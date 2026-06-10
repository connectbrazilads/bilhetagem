import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
