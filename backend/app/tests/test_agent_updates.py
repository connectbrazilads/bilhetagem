from pathlib import Path

from starlette.requests import Request
from sqlalchemy.orm import Session

from app.api.routes.agent_updates import agent_heartbeat, agent_version, create_queue_action, finish_queue_action, list_agents, poll_queue_actions
from app.core.config import settings
from app.models.agent_queue_action import AgentQueueActionStatus, AgentQueueActionType
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.agent import AgentHeartbeatPayload, AgentQueueActionCreate, AgentQueueActionResult


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
    db_session.add(actor)
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
