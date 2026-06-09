from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from api_client import BillingApiClient, CapturedPrintJob
from config import AgentConfig, config
from print_event_log import PrintEventLogReader
from snmp_probe import fetch_snmp_status

try:
    import win32con
    import win32print
    import win32api
except ImportError:  # pragma: no cover - development on non-Windows hosts
    win32con = None
    win32print = None
    win32api = None

import os
import tempfile

logger = logging.getLogger("printbilling.agent.spool")


class SpoolMonitor:
    def __init__(
        self,
        api_client: BillingApiClient,
        agent_config: AgentConfig = config,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_client = api_client
        self.config = agent_config
        self.sleep = sleep
        self._seen_jobs: set[str] = set()
        self._paused_jobs: dict[str, tuple[str, int | None]] = {}
        self._last_snmp_poll = 0.0
        self._event_log_reader = PrintEventLogReader(agent_config=self.config)

    def run_forever(self, should_stop: Callable[[], bool] | None = None) -> None:
        should_stop = should_stop or (lambda: False)
        if win32print is None:
            raise RuntimeError("pywin32 nao esta instalado ou o agente nao esta rodando em Windows")

        logger.info("PrintBilling Agent iniciado")
        while not should_stop():
            for printer_name in self._enum_printers():
                try:
                    self._process_printer(printer_name)
                except Exception:
                    logger.exception("Falha ao processar fila da impressora %s", printer_name)
            self._check_paused_jobs_actions()
            try:
                self._process_web_prints()
            except Exception:
                logger.exception("Falha ao processar impressões web")
            try:
                self._process_print_event_log()
            except Exception:
                logger.exception("Falha ao processar Event Log de impressao")
            self._process_printer_statuses_if_due()
            self.sleep(self.config.poll_interval_seconds)

    def _enum_printers(self) -> Iterable[str]:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        for printer in win32print.EnumPrinters(flags, self.config.spool_server, 2):
            yield printer["pPrinterName"]

    def _process_printer(self, printer_name: str) -> None:
        handle = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(handle, 0, -1, 2)
            for raw_job in jobs:
                key = f"{printer_name}:{raw_job.get('JobId')}"
                if key in self._seen_jobs:
                    continue
                self._seen_jobs.add(key)
                captured = self._capture_job(printer_name, raw_job)
                job_id = raw_job.get("JobId")

                if job_id is not None:
                    logger.info("Pausando trabalho ate decisao do servidor: %s", key)
                    win32print.SetJob(handle, job_id, 0, None, win32con.JOB_CONTROL_PAUSE)

                try:
                    decision = self.api_client.submit_job(captured)
                except Exception:
                    logger.exception("Falha ao registrar trabalho no servidor: %s", key)
                    if self.config.cancel_blocked_jobs:
                        self._cancel_job(handle, job_id)
                    else:
                        self._seen_jobs.discard(key)
                    continue
                
                status = decision.get("status")
                authorized = decision.get("authorized")
                
                if status == "pending_release":
                    logger.info("Mantendo trabalho pausado para liberacao segura: %s", key)
                    self._paused_jobs[key] = (printer_name, job_id)
                elif not authorized and self.config.cancel_blocked_jobs:
                    self._cancel_job(handle, job_id)
                elif not authorized:
                    logger.warning("Trabalho nao autorizado mantido pausado: %s", key)
                    self._paused_jobs[key] = (printer_name, job_id)
                elif job_id is not None:
                    logger.info("Servidor autorizou trabalho, retomando spooler: %s", key)
                    win32print.SetJob(handle, job_id, 0, None, win32con.JOB_CONTROL_RESUME)
        finally:
            win32print.ClosePrinter(handle)

    def _check_paused_jobs_actions(self) -> None:
        if not self._paused_jobs:
            return
            
        keys = list(self._paused_jobs.keys())
        try:
            actions = self.api_client.get_agent_actions(keys)
            for key, action in actions.items():
                if key not in self._paused_jobs:
                    continue
                printer_name, job_id = self._paused_jobs[key]
                if action == "resume":
                    logger.info("Liberando trabalho suspenso no spooler: %s", key)
                    handle = win32print.OpenPrinter(printer_name)
                    try:
                        win32print.SetJob(handle, job_id, 0, None, win32con.JOB_CONTROL_RESUME)
                    finally:
                        win32print.ClosePrinter(handle)
                    del self._paused_jobs[key]
                elif action == "delete":
                    logger.info("Cancelando/excluindo trabalho suspenso no spooler: %s", key)
                    handle = win32print.OpenPrinter(printer_name)
                    try:
                        win32print.SetJob(handle, job_id, 0, None, win32con.JOB_CONTROL_DELETE)
                    finally:
                        win32print.ClosePrinter(handle)
                    del self._paused_jobs[key]
        except Exception:
            logger.exception("Falha ao checar ações dos trabalhos pausados")

    def _capture_job(self, printer_name: str, raw_job: dict) -> CapturedPrintJob:
        pages = raw_job.get("TotalPages") or raw_job.get("PagesPrinted") or 1
        devmode = raw_job.get("pDevMode")
        is_color = bool(getattr(devmode, "Color", 1) == 2) if devmode else False
        # JOB_INFO_2 pointer fields use 'p' prefix (pUserName, pDocument, etc.)
        username = self._extract_username(printer_name, raw_job)
        logger.debug("Job fields: %s", list(raw_job.keys()))
        logger.info("Capturado job de '%s' na impressora '%s' (%d pags)", username, printer_name, max(int(pages), 1))
        return CapturedPrintJob(
            username=username,
            printer_name=printer_name,
            pages=max(int(pages), 1),
            is_color=is_color,
            external_job_id=str(raw_job.get("JobId")) if raw_job.get("JobId") is not None else None,
            document_name=raw_job.get("pDocument"),
            submitted_at=datetime.now(timezone.utc),
        )

    def _extract_username(self, printer_name: str, raw_job: dict) -> str:
        candidate_fields = ("pUserName", "UserName", "pNotifyName", "NotifyName", "Owner")
        for field in candidate_fields:
            username = self._clean_username(raw_job.get(field))
            if username:
                return username

        username = self._lookup_print_job_owner(printer_name, raw_job.get("JobId"))
        if username:
            return username

        configured = self._clean_username(self.config.default_username)
        if configured:
            return configured

        username = self._active_windows_username()
        if username:
            return username

        for env_name in ("USERNAME", "USERDOMAIN"):
            username = self._clean_username(os.getenv(env_name))
            if username and username.lower() not in {"system", "localsystem"}:
                return username

        logger.warning(
            "Nao foi possivel identificar usuario do job. Campos disponiveis: %s",
            {field: raw_job.get(field) for field in candidate_fields if raw_job.get(field)}
        )
        return "unknown"

    def _lookup_print_job_owner(self, printer_name: str, job_id: object) -> str | None:
        try:
            job_id_int = int(job_id)
        except (TypeError, ValueError):
            return None

        try:
            import win32com.client

            wmi = win32com.client.GetObject("winmgmts:")
            jobs = wmi.ExecQuery(f"SELECT Name, Owner FROM Win32_PrintJob WHERE JobId = {job_id_int}")
            fallback_owner = None
            for job in jobs:
                owner = self._clean_username(getattr(job, "Owner", None))
                if not owner:
                    continue
                fallback_owner = fallback_owner or owner
                job_name = str(getattr(job, "Name", ""))
                if job_name.lower().startswith(printer_name.lower()):
                    return owner
            return fallback_owner
        except Exception:
            logger.debug("Nao foi possivel consultar owner via WMI para job %s", job_id, exc_info=True)
            return None

    def _active_windows_username(self) -> str | None:
        try:
            import win32ts

            session_id = win32ts.WTSGetActiveConsoleSessionId()
            username = win32ts.WTSQuerySessionInformation(
                win32ts.WTS_CURRENT_SERVER_HANDLE,
                session_id,
                win32ts.WTSUserName,
            )
            return self._clean_username(username)
        except Exception:
            logger.debug("Nao foi possivel identificar usuario ativo do Windows", exc_info=True)
            return None

    @staticmethod
    def _clean_username(value: object) -> str | None:
        if value is None:
            return None
        username = str(value).strip()
        if not username or username.lower() in {"none", "unknown"}:
            return None
        if "\\" in username:
            username = username.rsplit("\\", 1)[-1]
        if "@" in username:
            username = username.split("@", 1)[0]
        return username.strip() or None

    def _cancel_job(self, printer_handle, job_id: int | None) -> None:
        if job_id is None:
            return
        logger.warning("Cancelando trabalho bloqueado no spooler: %s", job_id)
        win32print.SetJob(printer_handle, job_id, 0, None, win32con.JOB_CONTROL_DELETE)

    def _process_web_prints(self) -> None:
        try:
            web_jobs = self.api_client.get_agent_web_prints()
        except Exception:
            logger.warning("Não foi possível buscar as impressões web no servidor")
            return
            
        if not web_jobs:
            return
            
        for job in web_jobs:
            job_id = job["id"]
            printer_name = job["printer_name"]
            filename = job["filename"]
            
            logger.info("Encontrada impressão web liberada: ID %s, Impressora '%s', Arquivo '%s'", job_id, printer_name, filename)
            
            try:
                pdf_data = self.api_client.download_web_print_file(job_id)
            except Exception:
                logger.exception("Erro ao baixar arquivo para impressão web ID %s", job_id)
                continue
                
            fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix=f"webprint_{job_id}_")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(pdf_data)
                
                logger.info("Imprimindo silenciosamente %s na impressora %s", temp_path, printer_name)
                if win32api is not None:
                    try:
                        win32api.ShellExecute(0, "printto", temp_path, f'"{printer_name}"', ".", 0)
                        logger.info("Comando de impressão enviado com sucesso.")
                    except Exception as print_err:
                        logger.warning("Erro ao tentar chamar ShellExecute 'printto': %s. Continuando com a simulação.", print_err)
                else:
                    logger.info("win32api não disponível. Simulação de impressão silenciosa realizada.")
                
                self.api_client.confirm_web_printed(job_id)
                logger.info("Impressão web ID %s confirmada com sucesso no backend.", job_id)
            except Exception:
                logger.exception("Erro ao processar impressão web ID %s", job_id)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

    def _process_printer_statuses_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_snmp_poll < self.config.snmp_poll_interval_seconds:
            return
        self._last_snmp_poll = now

        try:
            printers = self.api_client.get_printers()
        except Exception:
            logger.exception("Falha ao buscar impressoras para monitoramento SNMP local")
            return

        for printer in printers:
            printer_id = printer.get("id")
            ip_address = printer.get("ip_address")
            if not printer_id or not ip_address:
                continue
            try:
                status = fetch_snmp_status(ip_address, self.config)
                self.api_client.update_printer_status(printer_id, status.as_payload())
                logger.info("Status SNMP atualizado para impressora %s (%s)", printer.get("name"), ip_address)
            except Exception as exc:
                logger.warning(
                    "Falha ao consultar SNMP local da impressora %s (%s): %s",
                    printer.get("name"),
                    ip_address,
                    exc,
                )

    def _process_print_event_log(self) -> None:
        if not self.config.use_print_event_log:
            return

        events = self._event_log_reader.read_new_printed_jobs()
        for event in events:
            try:
                decision = self.api_client.submit_job(event.job)
                logger.info(
                    "Evento PrintService registrado: record_id=%s usuario=%s impressora=%s paginas=%s status=%s",
                    event.record_id,
                    event.job.username,
                    event.job.printer_name,
                    event.job.pages,
                    decision.get("status"),
                )
            except Exception:
                logger.exception("Falha ao enviar evento PrintService record_id=%s para API", event.record_id)
