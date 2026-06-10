from pathlib import Path

from sqlalchemy.orm import Session

from app.api.routes.agent_updates import agent_version
from app.core.config import settings
from app.models.user import User, UserRole


def test_agent_version_requires_published_file_for_update(db_session: Session, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "agent_latest_version", "0.2.0")
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    monkeypatch.setattr(settings, "agent_download_filename", "PrintBillingAgent.exe")
    actor = User(username="agent-test", full_name="Agent Test", role=UserRole.admin, is_active=True)
    db_session.add(actor)
    db_session.commit()

    response = agent_version(current_version="0.1.0", _=actor)

    assert response.latest_version == "0.2.0"
    assert response.update_available is False
    assert response.download_url is None


def test_agent_version_reports_update_when_file_exists(db_session: Session, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "agent_latest_version", "0.2.0")
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    monkeypatch.setattr(settings, "agent_download_filename", "PrintBillingAgent.exe")
    (tmp_path / "PrintBillingAgent.exe").write_bytes(b"agent")
    actor = User(username="agent-test-2", full_name="Agent Test 2", role=UserRole.admin, is_active=True)
    db_session.add(actor)
    db_session.commit()

    response = agent_version(current_version="0.1.0", _=actor)

    assert response.update_available is True
    assert response.download_url == "/agent/download"
