from __future__ import annotations

import logging
import servicemanager
import win32event
import win32service
import win32serviceutil

import sys
from api_client import BillingApiClient
from spool_monitor import SpoolMonitor

SERVICE_NAME = "PrintBillingAgent"
SERVICE_DISPLAY_NAME = "Print Billing Agent"
SERVICE_DESCRIPTION = "Monitora o Windows Print Spooler e envia trabalhos de impressao para a API de bilhetagem."


class PrintBillingService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args) -> None:
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.monitor: SpoolMonitor | None = None

    def SvcStop(self) -> None:
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self) -> None:
        from config import config, get_app_dir
        log_file = get_app_dir() / "agent.log"
        logging.basicConfig(
            filename=str(log_file),
            level=getattr(logging, config.log_level, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(message)s"
        )
        logging.info(f"{SERVICE_NAME} iniciado")
        servicemanager.LogInfoMsg(f"{SERVICE_NAME} iniciado")
        try:
            self.monitor = SpoolMonitor(BillingApiClient(), sleep=self._sleep_or_stop)
            self.monitor.run_forever(should_stop=self._should_stop)
        except Exception as e:
            logging.exception("Erro fatal no monitor do spooler")
            try:
                servicemanager.LogErrorMsg(f"{SERVICE_NAME} falhou: {e}")
            except Exception:
                pass
            raise
        finally:
            try:
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
            except Exception:
                pass

    def _should_stop(self) -> bool:
        return win32event.WaitForSingleObject(self.stop_event, 0) == win32event.WAIT_OBJECT_0

    def _sleep_or_stop(self, seconds: float) -> None:
        timeout_ms = max(0, int(seconds * 1000))
        win32event.WaitForSingleObject(self.stop_event, timeout_ms)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrintBillingService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PrintBillingService)
