import sys
import types
from pathlib import Path

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

import api_client
from api_client import BillingApiClient
from config import AgentConfig


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, get_responses: list[FakeResponse]):
        self.get_responses = get_responses
        self.calls: list[tuple[str, str]] = []

    def post(self, url: str, **_kwargs) -> FakeResponse:
        self.calls.append(("POST", url))
        return FakeResponse(200, {"access_token": "token"})

    def get(self, url: str, **_kwargs) -> FakeResponse:
        self.calls.append(("GET", url))
        return self.get_responses.pop(0)


def make_client(fake_session: FakeSession, monkeypatch) -> BillingApiClient:
    monkeypatch.setattr(api_client.requests, "Session", lambda: fake_session)
    return BillingApiClient(
        AgentConfig(
            api_base_url="https://billing.example.com",
            api_username="agent",
            api_password="AgentPassword2026",
            organization_slug="default",
        )
    )


def test_agent_client_reads_minimal_runtime_settings_endpoint(monkeypatch):
    session = FakeSession([FakeResponse(200, {"safe_release_enabled": False})])
    client = make_client(session, monkeypatch)

    settings = client.get_settings()

    assert settings == {"safe_release_enabled": False}
    assert session.calls == [
        ("POST", "https://billing.example.com/auth/login"),
        ("GET", "https://billing.example.com/settings/agent"),
    ]


def test_agent_client_falls_back_to_legacy_settings_endpoint(monkeypatch):
    session = FakeSession(
        [
            FakeResponse(404, {"detail": "Not found"}),
            FakeResponse(200, {"safe_release_enabled": True, "default_monthly_quota": 500}),
        ]
    )
    client = make_client(session, monkeypatch)

    settings = client.get_settings()

    assert settings["safe_release_enabled"] is True
    assert session.calls == [
        ("POST", "https://billing.example.com/auth/login"),
        ("GET", "https://billing.example.com/settings/agent"),
        ("GET", "https://billing.example.com/settings"),
    ]
