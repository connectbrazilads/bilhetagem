from pathlib import Path

from starlette.requests import Request
from sqlalchemy.orm import Session

from app.api.routes.agent_updates import (
    agent_heartbeat,
    agent_version,
    create_bulk_queue_actions,
    create_queue_action,
    finish_queue_action,
    list_agent_releases,
    list_agents,
    poll_queue_actions,
)
from app.core.config import settings
from app.models.agent_queue_action import AgentQueueActionStatus, AgentQueueActionType
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User, UserRole
from app.schemas.agent import AgentHeartbeatPayload, AgentQueueActionCreate, AgentQueueActionResult, AgentQueueBulkActionCreate


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
    assert response.sha256 is not None


def test_agent_releases_use_manifest_and_checksums(db_session: Session, monkeypatch, tmp_path: Path):
    release_dir = tmp_path / "0.3.0"
    release_dir.mkdir()
    (release_dir / "PrintBillingAgent.exe").write_bytes(b"agent-v3")
    (release_dir / "PrintBillingAgentInstaller.exe").write_bytes(b"installer-v3")
    (tmp_path / "manifest.json").write_text(
        """
        {
          "versions": [
            {
              "version": "0.3.0",
              "channel": "stable",
              "notes": "Teste",
              "files": [
                {"kind": "agent", "filename": "PrintBillingAgent.exe", "signature_status": "Valid", "signer_subject": "CN=PrintBilling"},
                {"kind": "installer", "filename": "PrintBillingAgentInstaller.exe", "signature_status": "NotSigned"}
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "agent_latest_version", "0.3.0")
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    actor = User(username="release-admin", full_name="Release Admin", role=UserRole.admin, is_active=True)
    db_session.add(actor)
    db_session.commit()

    releases = list_agent_releases(_=actor)
    version = agent_version(current_version="0.2.0", _=actor)

    assert releases[0].version == "0.3.0"
    assert {file.kind for file in releases[0].files} == {"agent", "installer"}
    assert releases[0].files[0].sha256
    assert next(file.signature_status for file in releases[0].files if file.kind == "agent") == "Valid"
    assert version.update_available is True
    assert version.sha256 == next(file.sha256 for file in releases[0].files if file.kind == "agent")


def _request(ip_address: str = "10.0.0.10") -> Request:
    return Request({"type": "http", "headers": [], "client": (ip_address, 12345)})


def test_agent_heartbeat_creates_agent_and_local_queues(db_session: Session):
    actor = User(username="agent-heartbeat", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    payload = AgentHeartbeatPayload(
        agent_uid="pc-financeiro-abc123",
        computer_name="PC-FIN",
        os_user="diego",
        version="0.2.0",
        capture_mode="event_log",
        event_log_enabled=True,
        auto_update_enabled=True,
        queues=[
            {
                "queue_name": "KONICA Financeiro",
                "driver_name": "KONICA Driver",
                "port_name": "IP_192.168.1.125",
                "connection_type": "network",
                "ip_address": "192.168.1.125",
                "serial_number": "SN123",
                "fingerprint": "serial:sn123",
            }
        ],
    )

    response = agent_heartbeat(payload=payload, request=_request(), db=db_session, actor=actor)

    assert response.agent_uid == "pc-financeiro-abc123"
    assert response.computer_name == "PC-FIN"
    assert response.os_user == "diego"
    assert response.ip_address == "10.0.0.10"
    assert response.is_online is True
    assert response.aliases[0].queue_name == "KONICA Financeiro"
    assert response.aliases[0].ip_address == "192.168.1.125"


def test_agent_health_alerts_report_operational_issues(db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "agent_latest_version", "0.3.0")
    actor = User(username="agent-alerts", full_name="Agent Alerts", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-alerts",
            computer_name="PC-ALERT",
            version="0.2.0",
            capture_mode="spool",
            event_log_enabled=False,
            last_error="Falha ao ler fila",
            queues=[
                {
                    "queue_name": "USER",
                    "driver_name": "Driver",
                    "port_name": "USB001",
                    "connection_type": "usb",
                    "fingerprint": "queue:pc-alert|user|usb001|driver",
                }
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    alert_codes = {alert.code for alert in response.health_alerts}
    assert {"last_error", "event_log_disabled", "unbound_queues", "outdated_version"}.issubset(alert_codes)
    assert "offline" not in alert_codes


def test_list_agents_is_scoped_by_organization(db_session: Session):
    other_org = Organization(name="Outro Cliente", slug="outro-cliente", is_active=True)
    db_session.add(other_org)
    db_session.flush()
    actor_default = User(username="agent-org-a", full_name="A", role=UserRole.admin, is_active=True, organization_id=1)
    actor_other = User(username="agent-org-b", full_name="B", role=UserRole.admin, is_active=True, organization_id=other_org.id)
    db_session.add_all([actor_default, actor_other])
    db_session.commit()

    agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-a", computer_name="PC-A"),
        request=_request("10.0.0.1"),
        db=db_session,
        actor=actor_default,
    )
    agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-b", computer_name="PC-B"),
        request=_request("10.0.0.2"),
        db=db_session,
        actor=actor_other,
    )

    visible_agents = list_agents(db=db_session, actor=actor_default)

    assert [agent.agent_uid for agent in visible_agents] == ["agent-a"]


def test_remote_queue_action_lifecycle(db_session: Session):
    actor = User(username="queue-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA FISICA", ip_address="192.168.1.125", is_color=True)
    db_session.add_all([actor, printer])
    db_session.commit()
    agent = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-queue-1", computer_name="PC-QUEUE"),
        request=_request("10.0.0.5"),
        db=db_session,
        actor=actor,
    )

    action = create_queue_action(
        agent_id=agent.id,
        payload=AgentQueueActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="KONICA_FINANCEIRO",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            ip_address="192.168.1.125",
        ),
        db=db_session,
        actor=actor,
    )

    assert action.status == AgentQueueActionStatus.pending

    pending = poll_queue_actions(agent_uid="agent-queue-1", db=db_session, actor=actor)

    assert [item.id for item in pending] == [action.id]
    assert pending[0].status == AgentQueueActionStatus.running
    assert pending[0].dispatched_at is not None

    finished = finish_queue_action(
        action_id=action.id,
        payload=AgentQueueActionResult(status=AgentQueueActionStatus.succeeded, result_message="Fila criada"),
        db=db_session,
        actor=actor,
    )

    assert finished.status == AgentQueueActionStatus.succeeded
    assert finished.result_message == "Fila criada"
    assert finished.completed_at is not None
    alias = db_session.query(PrinterAlias).filter(PrinterAlias.queue_name == "KONICA_FINANCEIRO").one()
    assert alias.printer_id == printer.id
    assert alias.driver_name == "KONICA Driver"
    assert alias.ip_address == "192.168.1.125"
    result_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "agent_queue_action_finished", AuditLog.entity_id == action.id)
        .one()
    )
    assert result_audit.log_metadata["status"] == "succeeded"
    assert result_audit.log_metadata["printer_id"] == printer.id


def test_remote_queue_actions_are_scoped_by_organization(db_session: Session):
    other_org = Organization(name="Cliente B", slug="cliente-b", is_active=True)
    db_session.add(other_org)
    db_session.flush()
    actor_default = User(username="queue-org-a", full_name="A", role=UserRole.admin, is_active=True, organization_id=1)
    actor_other = User(username="queue-org-b", full_name="B", role=UserRole.admin, is_active=True, organization_id=other_org.id)
    db_session.add_all([actor_default, actor_other])
    db_session.commit()
    agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="shared-agent-id", computer_name="PC-A"),
        request=_request("10.0.0.1"),
        db=db_session,
        actor=actor_default,
    )
    agent_other = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="shared-agent-id", computer_name="PC-B"),
        request=_request("10.0.0.2"),
        db=db_session,
        actor=actor_other,
    )
    create_queue_action(
        agent_id=agent_other.id,
        payload=AgentQueueActionCreate(action_type=AgentQueueActionType.remove_queue, queue_name="Fila B"),
        db=db_session,
        actor=actor_other,
    )

    pending_default = poll_queue_actions(agent_uid="shared-agent-id", db=db_session, actor=actor_default)

    assert pending_default == []


def test_bulk_queue_action_applies_to_all_agents_in_organization(db_session: Session):
    other_org = Organization(name="Cliente Bulk B", slug="cliente-bulk-b", is_active=True)
    db_session.add(other_org)
    db_session.flush()
    actor_default = User(username="bulk-org-a", full_name="A", role=UserRole.admin, is_active=True, organization_id=1)
    actor_other = User(username="bulk-org-b", full_name="B", role=UserRole.admin, is_active=True, organization_id=other_org.id)
    printer = Printer(organization_id=1, name="KONICA_BULK", ip_address="192.168.1.126", is_color=True)
    db_session.add_all([actor_default, actor_other, printer])
    db_session.commit()
    agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="bulk-agent-1", computer_name="PC-1"),
        request=_request("10.0.0.11"),
        db=db_session,
        actor=actor_default,
    )
    agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="bulk-agent-2", computer_name="PC-2"),
        request=_request("10.0.0.12"),
        db=db_session,
        actor=actor_default,
    )
    agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="bulk-agent-other", computer_name="PC-OUTRO"),
        request=_request("10.0.0.13"),
        db=db_session,
        actor=actor_other,
    )

    actions = create_bulk_queue_actions(
        payload=AgentQueueBulkActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="KONICA_PADRAO",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            ip_address="192.168.1.126",
            apply_to_all=True,
        ),
        db=db_session,
        actor=actor_default,
    )

    assert len(actions) == 2
    assert {action.queue_name for action in actions} == {"KONICA_PADRAO"}
    assert {action.printer_id for action in actions} == {printer.id}
    assert poll_queue_actions(agent_uid="bulk-agent-other", db=db_session, actor=actor_other) == []
    assert len(db_session.query(AuditLog).filter(AuditLog.action == "agent_queue_action_created").all()) == 2


def test_bulk_queue_action_can_target_selected_agents(db_session: Session):
    actor = User(username="bulk-selected", full_name="Selected", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_SELECTED", ip_address="192.168.1.127", is_color=True)
    db_session.add_all([actor, printer])
    db_session.commit()
    agent_a = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="selected-agent-1", computer_name="PC-1"),
        request=_request("10.0.0.21"),
        db=db_session,
        actor=actor,
    )
    agent_b = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="selected-agent-2", computer_name="PC-2"),
        request=_request("10.0.0.22"),
        db=db_session,
        actor=actor,
    )
    agent_c = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="selected-agent-3", computer_name="PC-3"),
        request=_request("10.0.0.23"),
        db=db_session,
        actor=actor,
    )

    actions = create_bulk_queue_actions(
        payload=AgentQueueBulkActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="KONICA_GRUPO",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            ip_address="192.168.1.127",
            agent_ids=[agent_a.id, agent_c.id],
        ),
        db=db_session,
        actor=actor,
    )

    assert {action.agent_id for action in actions} == {agent_a.id, agent_c.id}
    assert poll_queue_actions(agent_uid=agent_b.agent_uid, db=db_session, actor=actor) == []
