from __future__ import annotations

import logging
import servicemanager
import win32event
import win32service
import win32serviceutil

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
        self.monitor = SpoolMonitor(BillingApiClient())

    def SvcStop(self) -> None:
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self) -> None:
        logging.basicConfig(level=logging.INFO)
        servicemanager.LogInfoMsg(f"{SERVICE_NAME} iniciado")
        self.monitor.run_forever(should_stop=self._should_stop)

    def _should_stop(self) -> bool:
        return win32event.WaitForSingleObject(self.stop_event, 0) == win32event.WAIT_OBJECT_0


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(PrintBillingService)
