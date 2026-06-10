from __future__ import annotations

import json
import logging
import hashlib
import re
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

from api_client import BillingApiClient, CapturedPrintJob
from config import AgentConfig, config, get_app_dir
from print_event_log import PrintEventLogReader
from snmp_probe import fetch_snmp_status
from version import AGENT_VERSION

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

JOB_CONTROL_PAUSE = getattr(win32print, "JOB_CONTROL_PAUSE", 1)
JOB_CONTROL_RESUME = getattr(win32print, "JOB_CONTROL_RESUME", 2)
JOB_CONTROL_DELETE = getattr(win32print, "JOB_CONTROL_DELETE", 5)


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
        self._last_settings_poll = 0.0
        self._last_update_check = 0.0
        self._last_heartbeat = 0.0
        self._last_queue_action_poll = 0.0
        self._update_started = False
        self._last_error: str | None = None
        self._diagnostic_logs: list[dict] = []
        self._server_safe_release_enabled = True
        self._event_log_reader = PrintEventLogReader(agent_config=self.config)
        self._agent_uid = self._load_agent_uid()
        self._computer_name = os.getenv("COMPUTERNAME") or socket.gethostname()

    def run_forever(self, should_stop: Callable[[], bool] | None = None) -> None:
        should_stop = should_stop or (lambda: False)
        if win32print is None:
            raise RuntimeError("pywin32 nao esta instalado ou o agente nao esta rodando em Windows")

        logger.info("PrintBilling Agent iniciado")
        self._record_log("info", "PrintBilling Agent iniciado", "service")
        while not should_stop():
            self._refresh_server_settings_if_due()
            self._send_heartbeat_if_due()
            self._process_queue_actions_if_due()
            if self._should_process_spool_jobs():
                for printer_name in self._enum_printers():
                    try:
                        self._process_printer(printer_name)
                    except Exception as exc:
                        logger.exception("Falha ao processar fila da impressora %s", printer_name)
                        self._record_error(f"Falha ao processar fila {printer_name}: {exc}")
            self._check_paused_jobs_actions()
            try:
                self._process_web_prints()
            except Exception as exc:
                logger.exception("Falha ao processar impressoes web")
                self._record_error(f"Falha ao processar impressoes web: {exc}")
            try:
                self._process_print_event_log()
            except Exception as exc:
                logger.exception("Falha ao processar Event Log de impressao")
                self._record_error(f"Falha ao processar Event Log de impressao: {exc}")
            self._process_printer_statuses_if_due()
            self._check_agent_update_if_due()
            self.sleep(self.config.poll_interval_seconds)

    def _should_process_spool_jobs(self) -> bool:
        return not (self.config.use_print_event_log and not self._server_safe_release_enabled)

    def _load_agent_uid(self) -> str:
        path = get_app_dir() / "agent_identity.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                uid = str(data.get("agent_uid") or "").strip()
                if uid:
                    return uid
            uid = f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
            path.write_text(json.dumps({"agent_uid": uid}, indent=2), encoding="utf-8")
            return uid
        except Exception:
            logger.warning("Nao foi possivel persistir identidade do agent")
            return f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"

    def _record_error(self, message: str) -> None:
        self._last_error = message[:500]
        self._record_log("error", message, "agent")

    def _record_log(self, level: str, message: str, source: str) -> None:
        self._diagnostic_logs.append(
            {
                "level": level,
                "message": message[:1000],
                "source": source[:80],
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._diagnostic_logs = self._diagnostic_logs[-100:]

    def _heartbeat_os_user(self) -> str | None:
        return self._active_windows_username() or self._clean_username(os.getenv("USERNAME"))

    def _send_heartbeat_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat < self.config.heartbeat_interval_seconds:
            return
        self._last_heartbeat = now

        queues = []
        try:
            for printer_name in self._enum_printers():
                metadata = self._queue_metadata(printer_name)
                queues.append(
                    {
                        "queue_name": printer_name,
                        "driver_name": metadata.get("printer_driver_name"),
                        "port_name": metadata.get("printer_port_name"),
                        "connection_type": metadata.get("printer_connection_type"),
                        "ip_address": metadata.get("printer_ip_address"),
                        "serial_number": metadata.get("printer_serial"),
                        "device_id": metadata.get("printer_device_id"),
                        "fingerprint": metadata.get("printer_fingerprint"),
                    }
                )
        except Exception as exc:
            logger.exception("Falha ao coletar filas para heartbeat")
            self._record_error(f"Falha ao coletar filas para heartbeat: {exc}")

        payload = {
            "agent_uid": self._agent_uid,
            "computer_name": self._computer_name,
            "os_user": self._heartbeat_os_user(),
            "version": AGENT_VERSION,
            "capture_mode": "event_log" if self.config.use_print_event_log else "spool",
            "event_log_enabled": self.config.use_print_event_log,
            "auto_update_enabled": self.config.auto_update_enabled,
            "last_error": self._last_error,
            "queues": queues,
            "logs": self._diagnostic_logs[-50:],
        }
        try:
            self.api_client.send_heartbeat(payload)
            if queues:
                logger.debug("Heartbeat enviado com %d fila(s)", len(queues))
            self._last_error = None
            self._diagnostic_logs.clear()
        except Exception as exc:
            logger.warning("Falha ao enviar heartbeat do agent: %s", exc)
            self._record_error(f"Falha ao enviar heartbeat: {exc}")

    def _process_queue_actions_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_queue_action_poll < self.config.queue_action_interval_seconds:
            return
        self._last_queue_action_poll = now

        try:
            actions = self.api_client.get_queue_actions(self._agent_uid)
        except Exception as exc:
            logger.warning("Falha ao buscar acoes remotas de filas: %s", exc)
            self._record_error(f"Falha ao buscar acoes remotas de filas: {exc}")
            return

        for action in actions:
            action_id = int(action["id"])
            try:
                message = self._execute_queue_action(action)
                self.api_client.finish_queue_action(action_id, "succeeded", message)
                logger.info("Acao remota de fila concluida: id=%s %s", action_id, message)
                self._record_log("info", f"Acao remota de fila concluida: id={action_id} {message}", "queue_action")
            except Exception as exc:
                message = str(exc)[:500]
                logger.exception("Falha ao executar acao remota de fila id=%s", action_id)
                self._record_error(f"Falha em acao remota de fila {action_id}: {message}")
                try:
                    self.api_client.finish_queue_action(action_id, "failed", message)
                except Exception:
                    logger.exception("Falha ao confirmar erro da acao remota de fila id=%s", action_id)

    def _execute_queue_action(self, action: dict) -> str:
        action_type = action.get("action_type")
        queue_name = self._clean_metadata(action.get("queue_name"))
        if not queue_name:
            raise RuntimeError("Nome da fila nao informado")
        if action_type == "create_queue":
            return self._create_managed_queue(
                queue_name=queue_name,
                driver_name=self._clean_metadata(action.get("driver_name")),
                port_name=self._clean_metadata(action.get("port_name")),
                ip_address=self._clean_metadata(action.get("ip_address")),
            )
        if action_type == "remove_queue":
            return self._remove_managed_queue(queue_name)
        raise RuntimeError(f"Acao desconhecida: {action_type}")

    @staticmethod
    def _ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _run_powershell(self, script: str) -> str:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            text=True,
            capture_output=True,
            timeout=90,
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.returncode != 0:
            raise RuntimeError(output or f"PowerShell retornou codigo {result.returncode}")
        return output[:500] or "OK"

    def _create_managed_queue(
        self,
        queue_name: str,
        driver_name: str | None,
        port_name: str | None,
        ip_address: str | None,
    ) -> str:
        if not driver_name:
            raise RuntimeError("Driver nao informado")
        if not port_name and not ip_address:
            raise RuntimeError("Porta/IP nao informado")

        queue = self._ps_quote(queue_name)
        driver = self._ps_quote(driver_name)
        port = self._ps_quote(port_name or "")
        ip = self._ps_quote(ip_address or "")
        script = f"""
$ErrorActionPreference = 'Stop'
$queueName = {queue}
$driverName = {driver}
$portName = {port}
$ipAddress = {ip}
if ([string]::IsNullOrWhiteSpace($portName)) {{ $portName = "IP_$ipAddress" }}
if (-not (Get-PrinterDriver -Name $driverName -ErrorAction SilentlyContinue)) {{ throw "Driver nao instalado: $driverName" }}
if (-not (Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue)) {{
  if ([string]::IsNullOrWhiteSpace($ipAddress)) {{ throw "Porta nao existe e IP nao informado: $portName" }}
  Add-PrinterPort -Name $portName -PrinterHostAddress $ipAddress
}}
if (-not (Get-Printer -Name $queueName -ErrorAction SilentlyContinue)) {{
  Add-Printer -Name $queueName -DriverName $driverName -PortName $portName
  "Fila criada: $queueName"
}} else {{
  "Fila ja existia: $queueName"
}}
"""
        return self._run_powershell(script)

    def _remove_managed_queue(self, queue_name: str) -> str:
        queue = self._ps_quote(queue_name)
        script = f"""
$ErrorActionPreference = 'Stop'
$queueName = {queue}
if (Get-Printer -Name $queueName -ErrorAction SilentlyContinue) {{
  Remove-Printer -Name $queueName
  "Fila removida: $queueName"
}} else {{
  "Fila nao encontrada: $queueName"
}}
"""
        return self._run_powershell(script)

    def _refresh_server_settings_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_settings_poll < 15:
            return
        self._last_settings_poll = now
        try:
            settings = self.api_client.get_settings()
            safe_release_enabled = bool(settings.get("safe_release_enabled", True))
            if safe_release_enabled != self._server_safe_release_enabled:
                logger.info("Follow-Me no servidor: %s", "ativado" if safe_release_enabled else "desativado")
            self._server_safe_release_enabled = safe_release_enabled
        except Exception:
            logger.exception("Falha ao buscar configuracoes do servidor")

    def _check_agent_update_if_due(self) -> None:
        if self._update_started or not self.config.auto_update_enabled:
            return
        now = time.monotonic()
        if now - self._last_update_check < self.config.update_check_interval_seconds:
            return
        self._last_update_check = now
        try:
            info = self.api_client.get_agent_version_info(AGENT_VERSION)
            if not info.get("update_available"):
                return
            latest_version = info.get("latest_version", "desconhecida")
            logger.info("Atualizacao do agent disponivel: atual=%s nova=%s", AGENT_VERSION, latest_version)
            update_bytes = self.api_client.download_agent_update()
            expected_sha256 = self._clean_metadata(info.get("sha256"))
            if not expected_sha256:
                raise RuntimeError("Servidor nao informou SHA256 da atualizacao do agent")
            actual_sha256 = hashlib.sha256(update_bytes).hexdigest()
            if actual_sha256.lower() != expected_sha256.lower():
                raise RuntimeError(
                    f"SHA256 da atualizacao invalido: esperado={expected_sha256} obtido={actual_sha256}"
                )
            update_path = get_app_dir() / "PrintBillingAgent.update.exe"
            update_path.write_bytes(update_bytes)
            logger.info("Atualizacao do agent baixada e verificada em %s", update_path)
            if getattr(sys, "frozen", False):
                self._schedule_self_update(update_path)
            else:
                logger.info("Ambiente de desenvolvimento detectado; atualizacao nao aplicada automaticamente")
        except Exception:
            logger.exception("Falha ao verificar/baixar atualizacao do agent")

    def _schedule_self_update(self, update_path) -> None:
        current_exe = Path(sys.executable)
        backup_path = current_exe.with_name(f"{current_exe.name}.bak")
        script_path = get_app_dir() / "apply_agent_update.cmd"
        script = "\r\n".join(
            [
                "@echo off",
                "setlocal",
                "timeout /t 3 /nobreak > nul",
                "sc stop PrintBillingAgent > nul 2>&1",
                "timeout /t 5 /nobreak > nul",
                f'copy /Y "{current_exe}" "{backup_path}" > nul',
                "if errorlevel 1 goto rollback",
                f'copy /Y "{update_path}" "{current_exe}" > nul',
                "if errorlevel 1 goto rollback",
                "sc start PrintBillingAgent > nul 2>&1",
                "if errorlevel 1 goto rollback",
                "goto cleanup",
                ":rollback",
                f'copy /Y "{backup_path}" "{current_exe}" > nul 2>&1',
                "sc start PrintBillingAgent > nul 2>&1",
                ":cleanup",
                f'del "{update_path}" > nul 2>&1',
                f'del "{backup_path}" > nul 2>&1',
                f'del "{script_path}" > nul 2>&1',
            ]
        )
        script_path.write_text(script, encoding="utf-8")
        subprocess.Popen(["cmd.exe", "/c", str(script_path)], close_fds=True)
        self._update_started = True
        logger.info("Atualizacao agendada; o servico sera reiniciado")

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
                    win32print.SetJob(handle, job_id, 0, None, JOB_CONTROL_PAUSE)

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
                    win32print.SetJob(handle, job_id, 0, None, JOB_CONTROL_RESUME)
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
                        win32print.SetJob(handle, job_id, 0, None, JOB_CONTROL_RESUME)
                    finally:
                        win32print.ClosePrinter(handle)
                    del self._paused_jobs[key]
                elif action == "delete":
                    logger.info("Cancelando/excluindo trabalho suspenso no spooler: %s", key)
                    handle = win32print.OpenPrinter(printer_name)
                    try:
                        win32print.SetJob(handle, job_id, 0, None, JOB_CONTROL_DELETE)
                    finally:
                        win32print.ClosePrinter(handle)
                    del self._paused_jobs[key]
        except Exception:
            logger.exception("Falha ao checar acoes dos trabalhos pausados")

    def _capture_job(self, printer_name: str, raw_job: dict) -> CapturedPrintJob:
        pages = raw_job.get("TotalPages") or raw_job.get("PagesPrinted") or 1
        devmode = raw_job.get("pDevMode")
        is_color = bool(getattr(devmode, "Color", 1) == 2) if devmode else False
        # JOB_INFO_2 pointer fields use 'p' prefix (pUserName, pDocument, etc.)
        username = self._extract_username(printer_name, raw_job)
        metadata = self._queue_metadata(printer_name)
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
            **metadata,
        )

    def _queue_metadata(self, printer_name: str) -> dict:
        data = {
            "agent_uid": self._agent_uid,
            "computer_name": self._computer_name,
            "queue_name": printer_name,
            "printer_driver_name": None,
            "printer_port_name": None,
            "printer_connection_type": "unknown",
            "printer_ip_address": None,
            "printer_serial": None,
            "printer_device_id": None,
            "printer_fingerprint": None,
        }
        try:
            handle = win32print.OpenPrinter(printer_name)
            try:
                info = win32print.GetPrinter(handle, 2)
            finally:
                win32print.ClosePrinter(handle)
            port_name = self._clean_metadata(info.get("pPortName"))
            driver_name = self._clean_metadata(info.get("pDriverName"))
            data["printer_port_name"] = port_name
            data["printer_driver_name"] = driver_name
            data["printer_connection_type"] = self._connection_type(printer_name, port_name)
            data["printer_ip_address"] = self._extract_ip(port_name)
            wmi_metadata = self._wmi_printer_metadata(printer_name)
            if wmi_metadata.get("port_name") and not data["printer_port_name"]:
                data["printer_port_name"] = wmi_metadata["port_name"]
            if wmi_metadata.get("driver_name") and not data["printer_driver_name"]:
                data["printer_driver_name"] = wmi_metadata["driver_name"]
            if wmi_metadata.get("device_id"):
                data["printer_device_id"] = wmi_metadata["device_id"]
            if data["printer_connection_type"] == "usb":
                data["printer_device_id"] = data["printer_device_id"] or self._usb_device_id(
                    data["computer_name"],
                    data["printer_port_name"],
                    data["printer_driver_name"],
                )
        except Exception:
            logger.debug("Nao foi possivel ler metadata da fila %s", printer_name, exc_info=True)

        data["printer_fingerprint"] = self._printer_fingerprint(data)
        return data

    @staticmethod
    def _clean_metadata(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _connection_type(self, printer_name: str, port_name: str | None) -> str:
        port = (port_name or "").lower()
        if printer_name.startswith("\\\\"):
            return "shared"
        if port.startswith(("usb", "dot4")):
            return "usb"
        if self._extract_ip(port_name) or port.startswith(("ip_", "tcp", "wsd")):
            return "network"
        if port.startswith(("lpt", "com")):
            return "local"
        return "unknown"

    @staticmethod
    def _extract_ip(value: str | None) -> str | None:
        if not value:
            return None
        match = re.search(r"(?:(?:IP_)?)(\d{1,3}(?:\.\d{1,3}){3})", value, flags=re.IGNORECASE)
        if not match:
            return None
        octets = match.group(1).split(".")
        if all(0 <= int(octet) <= 255 for octet in octets):
            return match.group(1)
        return None

    @staticmethod
    def _printer_fingerprint(metadata: dict) -> str:
        if metadata.get("printer_serial"):
            return f"serial:{metadata['printer_serial']}".lower()
        if metadata.get("printer_ip_address"):
            return f"ip:{metadata['printer_ip_address']}".lower()
        if metadata.get("printer_device_id"):
            if metadata.get("printer_connection_type") == "usb":
                computer = metadata.get("computer_name") or ""
                return f"usb:{computer}|{metadata['printer_device_id']}".lower()
            return f"device:{metadata['printer_device_id']}".lower()
        parts = [
            metadata.get("computer_name") or "",
            metadata.get("queue_name") or "",
            metadata.get("printer_port_name") or "",
            metadata.get("printer_driver_name") or "",
        ]
        return "queue:" + "|".join(part.strip().lower() for part in parts)

    @staticmethod
    def _usb_device_id(computer_name: str | None, port_name: str | None, driver_name: str | None) -> str | None:
        parts = [part for part in (computer_name, port_name, driver_name) if part]
        return "|".join(parts) if parts else None

    def _wmi_printer_metadata(self, printer_name: str) -> dict[str, str | None]:
        metadata: dict[str, str | None] = {"port_name": None, "driver_name": None, "device_id": None}
        try:
            import win32com.client

            wmi = win32com.client.GetObject("winmgmts:")
            for printer in wmi.ExecQuery("SELECT Name, PortName, DriverName, DeviceID, PNPDeviceID FROM Win32_Printer"):
                name = self._clean_metadata(getattr(printer, "Name", None))
                if not name or name.lower() != printer_name.lower():
                    continue
                metadata["port_name"] = self._clean_metadata(getattr(printer, "PortName", None))
                metadata["driver_name"] = self._clean_metadata(getattr(printer, "DriverName", None))
                metadata["device_id"] = self._clean_metadata(getattr(printer, "PNPDeviceID", None)) or self._clean_metadata(getattr(printer, "DeviceID", None))
                return metadata
        except Exception:
            logger.debug("Nao foi possivel consultar metadata WMI da fila %s", printer_name, exc_info=True)
        return metadata

    def _extract_username(self, printer_name: str, raw_job: dict) -> str:
        configured = self._clean_username(self.config.default_username)
        candidate_fields = ("pUserName", "UserName", "pNotifyName", "NotifyName", "Owner")
        for field in candidate_fields:
            username = self._clean_username(raw_job.get(field))
            if username:
                return self._preferred_username(username, configured)

        username = self._lookup_print_job_owner(printer_name, raw_job.get("JobId"))
        if username:
            return self._preferred_username(username, configured)

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

    @staticmethod
    def _preferred_username(username: str, configured: str | None) -> str:
        if configured and username.lower() in {"user", "usuario", "unknown", "system", "localsystem"}:
            return configured
        return username

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
        win32print.SetJob(printer_handle, job_id, 0, None, JOB_CONTROL_DELETE)

    def _process_web_prints(self) -> None:
        try:
            web_jobs = self.api_client.get_agent_web_prints()
        except Exception:
            logger.warning("Nao foi possivel buscar as impressoes web no servidor")
            return
            
        if not web_jobs:
            return
            
        for job in web_jobs:
            job_id = job["id"]
            printer_name = job["printer_name"]
            filename = job["filename"]
            
            logger.info("Encontrada impressao web liberada: ID %s, Impressora '%s', Arquivo '%s'", job_id, printer_name, filename)
            
            try:
                pdf_data = self.api_client.download_web_print_file(job_id)
            except Exception:
                logger.exception("Erro ao baixar arquivo para impressao web ID %s", job_id)
                continue
                
            fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix=f"webprint_{job_id}_")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(pdf_data)
                
                logger.info("Imprimindo silenciosamente %s na impressora %s", temp_path, printer_name)
                if win32api is not None:
                    try:
                        win32api.ShellExecute(0, "printto", temp_path, f'"{printer_name}"', ".", 0)
                        logger.info("Comando de impressao enviado com sucesso.")
                    except Exception as print_err:
                        logger.warning("Erro ao tentar chamar ShellExecute 'printto': %s. Continuando com a simulacao.", print_err)
                else:
                    logger.info("win32api nao disponivel. Simulacao de impressao silenciosa realizada.")
                
                self.api_client.confirm_web_printed(job_id)
                logger.info("Impressao web ID %s confirmada com sucesso no backend.", job_id)
            except Exception:
                logger.exception("Erro ao processar impressao web ID %s", job_id)
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
                metadata = self._queue_metadata(event.job.printer_name)
                event_job = replace(event.job, **metadata)
                decision = self.api_client.submit_job(event_job)
                logger.info(
                    "Evento PrintService registrado: record_id=%s usuario=%s impressora=%s paginas=%s status=%s",
                    event.record_id,
                    event_job.username,
                    event_job.printer_name,
                    event_job.pages,
                    decision.get("status"),
                )
                self._event_log_reader.mark_processed(event.record_id)
            except Exception:
                logger.exception("Falha ao enviar evento PrintService record_id=%s para API", event.record_id)
