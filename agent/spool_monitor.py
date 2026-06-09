from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from api_client import BillingApiClient, CapturedPrintJob
from config import AgentConfig, config

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
        self._paused_jobs: dict[str, tuple[str, int]] = {}

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
                decision = self.api_client.submit_job(captured)
                
                status = decision.get("status")
                authorized = decision.get("authorized")
                
                if status == "pending_release":
                    logger.info("Pausando trabalho para liberação segura: %s", key)
                    win32print.SetJob(handle, raw_job.get("JobId"), 0, None, win32con.JOB_CONTROL_PAUSE)
                    self._paused_jobs[key] = (printer_name, raw_job.get("JobId"))
                elif not authorized and self.config.cancel_blocked_jobs:
                    self._cancel_job(handle, raw_job.get("JobId"))
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
        return CapturedPrintJob(
            username=raw_job.get("UserName") or "unknown",
            printer_name=printer_name,
            pages=max(int(pages), 1),
            is_color=is_color,
            external_job_id=str(raw_job.get("JobId")) if raw_job.get("JobId") is not None else None,
            document_name=raw_job.get("pDocument"),
            submitted_at=datetime.now(timezone.utc),
        )

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
