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
from config import AgentConfig
import print_event_log
import spool_monitor
from spool_monitor import SpoolMonitor
from update_script import build_self_update_script


def test_self_update_script_preserves_backup_after_success():
    current_exe = Path(r"C:\Program Files\PrintBillingAgent\PrintBillingAgent.exe")
    update_path = Path(r"C:\Program Files\PrintBillingAgent\PrintBillingAgent.update.exe")
    backup_path = Path(r"C:\Program Files\PrintBillingAgent\PrintBillingAgent.exe.bak")
    log_path = Path(r"C:\Program Files\PrintBillingAgent\agent_update.log")
    script_path = Path(r"C:\Program Files\PrintBillingAgent\apply_agent_update.cmd")

    script = build_self_update_script(current_exe, update_path, backup_path, log_path, script_path)

    assert f'copy /Y "{current_exe}" "{backup_path}" > nul' in script
    assert f'copy /Y "{backup_path}" "{current_exe}" > nul 2>&1' in script
    assert f'del "{update_path}" > nul 2>&1' in script
    assert f'del "{script_path}" > nul 2>&1' in script
    assert f'del "{backup_path}"' not in script
    assert "Backup preservado" in script
    assert "Falha ao criar backup; codigo=%ERRORLEVEL%" in script
    assert "Falha ao substituir executavel; codigo=%ERRORLEVEL%" in script
    assert "Falha ao iniciar servico atualizado; codigo=%ERRORLEVEL%" in script
    assert "Falha ao restaurar backup; codigo=%ERRORLEVEL%" in script
    assert "Falha ao iniciar servico apos rollback; codigo=%ERRORLEVEL%" in script


def test_agent_update_failure_is_reported_in_diagnostics(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(spool_monitor, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(print_event_log, "get_app_dir", lambda: tmp_path)

    class FakeApiClient:
        def get_agent_version_info(self, current_version: str) -> dict:
            return {
                "latest_version": "0.3.0",
                "update_available": True,
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            }

        def download_agent_update(self) -> bytes:
            return b"agent-update-binary"

    monitor = SpoolMonitor(
        FakeApiClient(),
        agent_config=AgentConfig(auto_update_enabled=True, update_check_interval_seconds=0),
        sleep=lambda _: None,
    )

    monitor._check_agent_update_if_due()

    assert monitor._last_error is not None
    assert "SHA256 da atualizacao invalido" in monitor._last_error
    assert any(
        log["level"] == "error" and "Falha ao verificar/baixar atualizacao do agent" in log["message"]
        for log in monitor._diagnostic_logs
    )


def test_queue_action_processing_continues_after_malformed_action(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(spool_monitor, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(print_event_log, "get_app_dir", lambda: tmp_path)

    class FakeApiClient:
        def __init__(self):
            self.finished = []

        def get_queue_actions(self, agent_uid: str) -> list[dict]:
            return [
                {"action_type": "remove_queue", "queue_name": "SEM_ID"},
                {"id": 11, "action_type": "unknown", "queue_name": "FALHA"},
                {"id": 12, "action_type": "remove_queue", "queue_name": "OK"},
            ]

        def finish_queue_action(self, action_id: int, status: str, result_message: str | None = None, agent_uid: str | None = None) -> dict:
            self.finished.append((action_id, status, result_message, agent_uid))
            return {"id": action_id, "status": status}

    api_client = FakeApiClient()
    monitor = SpoolMonitor(
        api_client,
        agent_config=AgentConfig(queue_action_interval_seconds=0),
        sleep=lambda _: None,
    )
    monkeypatch.setattr(monitor, "_remove_managed_queue", lambda queue_name: f"Fila removida: {queue_name}")

    monitor._process_queue_actions_if_due()

    assert [entry[0] for entry in api_client.finished] == [11, 12]
    assert api_client.finished[0][1] == "failed"
    assert "Acao desconhecida" in api_client.finished[0][2]
    assert api_client.finished[1] == (12, "succeeded", "Fila removida: OK", monitor._agent_uid)
    assert monitor._last_error is not None
    assert "desconhecida" in monitor._last_error
