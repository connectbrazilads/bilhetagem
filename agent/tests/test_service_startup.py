import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("requests", types.SimpleNamespace(Session=lambda: None))
sys.modules.setdefault(
    "tenacity",
    types.SimpleNamespace(
        retry=lambda *_, **__: (lambda function: function),
        stop_after_attempt=lambda *_: None,
        wait_exponential=lambda **_: None,
    ),
)


class FakeServiceFramework:
    def __init__(self, _args) -> None:
        self.statuses = []

    def ReportServiceStatus(self, status) -> None:
        self.statuses.append(status)


sys.modules.setdefault(
    "servicemanager",
    types.SimpleNamespace(
        LogInfoMsg=lambda _message: None,
        LogErrorMsg=lambda _message: None,
        Initialize=lambda: None,
        PrepareToHostSingle=lambda _service: None,
        StartServiceCtrlDispatcher=lambda: None,
    ),
)
sys.modules.setdefault(
    "win32event",
    types.SimpleNamespace(
        CreateEvent=lambda *_args: object(),
        SetEvent=lambda _event: None,
        WaitForSingleObject=lambda *_args: 1,
        WAIT_OBJECT_0=0,
    ),
)
sys.modules.setdefault("win32service", types.SimpleNamespace(SERVICE_STOP_PENDING=3, SERVICE_STOPPED=1))
sys.modules.setdefault(
    "win32serviceutil",
    types.SimpleNamespace(
        ServiceFramework=FakeServiceFramework,
        HandleCommandLine=lambda _service: None,
    ),
)

import service


def test_service_constructor_defers_api_client_until_runtime(monkeypatch):
    calls = []

    def fake_api_client():
        calls.append("client")
        raise RuntimeError("config invalida")

    monkeypatch.setattr(service, "BillingApiClient", fake_api_client)

    service.PrintBillingService([])

    assert calls == []


def test_service_logs_startup_failure_after_logging_is_configured(monkeypatch):
    errors = []
    exceptions = []

    def fake_api_client():
        raise RuntimeError("senha insegura")

    monkeypatch.setattr(service, "BillingApiClient", fake_api_client)
    monkeypatch.setattr(service.logging, "basicConfig", lambda **_kwargs: None)
    monkeypatch.setattr(service.logging, "exception", lambda message: exceptions.append(message))
    monkeypatch.setattr(service.servicemanager, "LogErrorMsg", lambda message: errors.append(message))

    instance = service.PrintBillingService([])

    with pytest.raises(RuntimeError, match="senha insegura"):
        instance.SvcDoRun()

    assert exceptions == ["Erro fatal no monitor do spooler"]
    assert errors == ["PrintBillingAgent falhou: senha insegura"]


def test_service_sleep_waits_on_stop_event(monkeypatch):
    waits = []
    sentinel = object()

    monkeypatch.setattr(service.win32event, "CreateEvent", lambda *_args: sentinel)
    monkeypatch.setattr(service.win32event, "WaitForSingleObject", lambda event, timeout: waits.append((event, timeout)) or 1)

    instance = service.PrintBillingService([])

    instance._sleep_or_stop(1.25)

    assert waits == [(sentinel, 1250)]
