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
