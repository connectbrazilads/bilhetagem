import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.api.routes.agent_updates import (
    agent_heartbeat,
    agent_version,
    create_bulk_queue_actions,
    create_queue_action,
    download_agent_release_file,
    download_agent_release_checksums,
    finish_queue_action,
    get_agent_detail,
    list_agent_deployment_organizations,
    list_agent_releases,
    list_agents,
    poll_queue_actions,
)
from app.core.config import settings
from app.services.agent_release_service import published_agent_version
from app.models.agent_queue_action import AgentQueueActionStatus, AgentQueueActionType
from app.models.agent_log import AgentLog
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.print_agent import PrintAgent
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.print_job import JobStatus, PrintJob
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


def test_agent_releases_fall_back_to_legacy_file_when_manifest_is_invalid(db_session: Session, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "agent_latest_version", "0.2.0")
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    monkeypatch.setattr(settings, "agent_download_filename", "PrintBillingAgent.exe")
    (tmp_path / "manifest.json").write_text("{invalid-json", encoding="utf-8")
    (tmp_path / "PrintBillingAgent.exe").write_bytes(b"legacy-agent")
    actor = User(username="invalid-manifest-admin", full_name="Release Admin", role=UserRole.admin, is_active=True)
    db_session.add(actor)
    db_session.commit()

    releases = list_agent_releases(_=actor)
    version = agent_version(current_version="0.1.0", _=actor)

    assert [release.version for release in releases] == ["0.2.0"]
    assert releases[0].signature_status == "unsigned"
    assert releases[0].files[0].sha256 == hashlib.sha256(b"legacy-agent").hexdigest()
    assert version.update_available is True
    assert version.sha256 == hashlib.sha256(b"legacy-agent").hexdigest()


def test_agent_releases_ignore_manifest_entries_without_safe_filename(db_session: Session, monkeypatch, tmp_path: Path):
    broken_dir = tmp_path / "0.4.0"
    broken_dir.mkdir()
    valid_dir = tmp_path / "0.3.0"
    valid_dir.mkdir()
    (valid_dir / "PrintBillingAgent.exe").write_bytes(b"agent-v3")
    (tmp_path / "manifest.json").write_text(
        """
        {
          "versions": [
            {
              "version": "0.4.0",
              "published_at": "2026-04-01T00:00:00Z",
              "files": [{"kind": "agent"}]
            },
            {
              "version": "0.3.0",
              "channel": 123,
              "published_at": "2026-03-01T00:00:00Z",
              "notes": {"bad": true},
              "files": [{"kind": "agent", "filename": "PrintBillingAgent.exe", "signature_status": 456, "signer_subject": ["bad"]}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "agent_latest_version", "0.2.0")
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    actor = User(username="unsafe-manifest-admin", full_name="Release Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    releases = list_agent_releases(_=actor)
    version = agent_version(current_version="0.2.0", _=actor)

    assert [release.version for release in releases] == ["0.4.0", "0.3.0"]
    assert releases[0].files == []
    assert releases[0].signature_status == "empty"
    assert releases[1].channel == "123"
    assert releases[1].notes is None
    assert releases[1].files[0].signature_status == "456"
    assert releases[1].files[0].signer_subject is None
    assert version.latest_version == "0.3.0"
    assert version.update_available is True
    assert version.sha256 == hashlib.sha256(b"agent-v3").hexdigest()


def test_agent_releases_ignore_unsafe_versions_and_malformed_entries(db_session: Session, monkeypatch, tmp_path: Path):
    safe_dir = tmp_path / "0.5.0"
    safe_dir.mkdir()
    (safe_dir / "PrintBillingAgent.exe").write_bytes(b"agent-v5")
    (tmp_path / "manifest.json").write_text(
        """
        {
          "versions": [
            "bad-entry",
            {
              "version": "../0.6.0",
              "published_at": "2026-06-01T00:00:00Z",
              "files": [{"kind": "agent", "filename": "PrintBillingAgent.exe"}]
            },
            {
              "version": "0.5.1",
              "published_at": "2026-05-02T00:00:00Z",
              "files": {"kind": "agent", "filename": "PrintBillingAgent.exe"}
            },
            {
              "version": "0.5.0",
              "published_at": "2026-05-01T00:00:00Z",
              "files": [{"kind": "agent", "filename": "PrintBillingAgent.exe"}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "agent_latest_version", "0.2.0")
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    actor = User(username="unsafe-version-admin", full_name="Release Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    releases = list_agent_releases(_=actor)
    version = agent_version(current_version="0.2.0", _=actor)

    assert [release.version for release in releases] == ["0.5.1", "0.5.0"]
    assert releases[0].files == []
    assert releases[1].files[0].download_url == "/agent/releases/0.5.0/download?filename=PrintBillingAgent.exe"
    assert published_agent_version() == "0.5.0"
    assert version.latest_version == "0.5.0"
    assert version.update_available is True
    assert version.sha256 == hashlib.sha256(b"agent-v5").hexdigest()


def test_agent_release_downloads_reject_unsafe_versions(db_session: Session, monkeypatch, tmp_path: Path):
    release_dir = tmp_path / "0.5.0"
    release_dir.mkdir()
    (release_dir / "PrintBillingAgent.exe").write_bytes(b"agent")
    (tmp_path / "manifest.json").write_text(
        """
        {
          "versions": [
            {
              "version": "0.5.0",
              "published_at": "2026-05-01T00:00:00Z",
              "files": [{"kind": "agent", "filename": "PrintBillingAgent.exe"}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    actor = User(username="unsafe-release-download-admin", full_name="Release Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    with pytest.raises(HTTPException) as download_exc:
        download_agent_release_file(version="../0.5.0", filename="PrintBillingAgent.exe", _=actor)
    with pytest.raises(HTTPException) as checksums_exc:
        download_agent_release_checksums(version="../0.5.0", _=actor)

    assert download_exc.value.status_code == 400
    assert checksums_exc.value.status_code == 400


def test_agent_releases_use_manifest_and_checksums(db_session: Session, monkeypatch, tmp_path: Path):
    old_release_dir = tmp_path / "0.2.0"
    old_release_dir.mkdir()
    (old_release_dir / "PrintBillingAgent.exe").write_bytes(b"agent-v2")
    release_dir = tmp_path / "0.3.0"
    release_dir.mkdir()
    (release_dir / "PrintBillingAgent.exe").write_bytes(b"agent-v3")
    (release_dir / "PrintBillingAgentInstaller.exe").write_bytes(b"installer-v3")
    (tmp_path / "manifest.json").write_text(
        """
        {
          "versions": [
            {
              "version": "0.2.0",
              "channel": "stable",
              "published_at": "2026-01-01T00:00:00Z",
              "notes": "Antiga",
              "files": [
                {"kind": "agent", "filename": "PrintBillingAgent.exe", "signature_status": "NotSigned"}
              ]
            },
            {
              "version": "0.3.0",
              "channel": "stable",
              "published_at": "2026-02-01T00:00:00Z",
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

    assert [release.version for release in releases] == ["0.3.0", "0.2.0"]
    assert releases[0].checksums_url == "/agent/releases/0.3.0/checksums"
    assert releases[0].signature_status == "mixed"
    assert releases[0].signature_summary == "Assinatura parcial: nem todos os artefatos estao assinados"
    assert releases[1].signature_status == "unsigned"
    assert {file.kind for file in releases[0].files} == {"agent", "installer"}
    assert releases[0].files[0].sha256
    assert next(file.signature_status for file in releases[0].files if file.kind == "agent") == "Valid"
    assert version.update_available is True
    assert version.sha256 == next(file.sha256 for file in releases[0].files if file.kind == "agent")

    checksums = download_agent_release_checksums(version="0.3.0", _=actor)
    body = checksums.body.decode("utf-8")
    assert "PrintBillingAgent.exe" in body
    assert "PrintBillingAgentInstaller.exe" in body
    assert checksums.headers["content-disposition"] == "attachment; filename=SHA256SUMS-0.3.0.txt"


def test_agent_releases_publish_actual_file_hash_when_manifest_is_stale(db_session: Session, monkeypatch, tmp_path: Path):
    release_dir = tmp_path / "0.3.1"
    release_dir.mkdir()
    release_file = release_dir / "PrintBillingAgent.exe"
    release_file.write_bytes(b"real-agent-binary")
    (tmp_path / "manifest.json").write_text(
        """
        {
          "versions": [
            {
              "version": "0.3.1",
              "published_at": "2026-02-02T00:00:00Z",
              "files": [
                {
                  "kind": "agent",
                  "filename": "PrintBillingAgent.exe",
                  "size_bytes": 999,
                  "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    actor = User(username="stale-manifest-admin", full_name="Release Admin", role=UserRole.admin, is_active=True)
    db_session.add(actor)
    db_session.commit()

    release = list_agent_releases(_=actor)[0]
    checksums = download_agent_release_checksums(version="0.3.1", _=actor)

    actual_sha = hashlib.sha256(b"real-agent-binary").hexdigest()
    assert release.files[0].size_bytes == len(b"real-agent-binary")
    assert release.files[0].sha256 == actual_sha
    assert checksums.body.decode("utf-8") == f"{actual_sha}  PrintBillingAgent.exe\n"


def test_agent_version_uses_newest_published_manifest_release(db_session: Session, monkeypatch, tmp_path: Path):
    old_release_dir = tmp_path / "0.3.0"
    old_release_dir.mkdir()
    (old_release_dir / "PrintBillingAgent.exe").write_bytes(b"agent-v3")
    latest_release_dir = tmp_path / "0.4.0"
    latest_release_dir.mkdir()
    latest_file = latest_release_dir / "PrintBillingAgent.exe"
    latest_file.write_bytes(b"agent-v4")
    (tmp_path / "manifest.json").write_text(
        """
        {
          "versions": [
            {
              "version": "0.3.0",
              "published_at": "2026-03-01T00:00:00Z",
              "files": [{"kind": "agent", "filename": "PrintBillingAgent.exe"}]
            },
            {
              "version": "0.4.0",
              "published_at": "2026-04-01T00:00:00Z",
              "files": [{"kind": "agent", "filename": "PrintBillingAgent.exe"}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "agent_latest_version", "0.2.0")
    monkeypatch.setattr(settings, "agent_download_dir", str(tmp_path))
    actor = User(username="manifest-admin", full_name="Manifest Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    version = agent_version(current_version="0.3.0", _=actor)
    heartbeat = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-manifest-version", version="0.3.0"),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    assert version.latest_version == "0.4.0"
    assert version.update_available is True
    assert version.sha256 == hashlib.sha256(b"agent-v4").hexdigest()
    assert any(alert.code == "outdated_version" and "0.4.0" in alert.message for alert in heartbeat.health_alerts)


def test_deployment_organizations_are_scoped_for_download_commands(db_session: Session):
    other_org = Organization(name="Cliente Download", slug="cliente-download", is_active=True)
    third_org = Organization(name="Cliente Inativo Download", slug="cliente-inativo-download", is_active=False)
    suspended_org = Organization(name="Cliente Suspenso Download", slug="cliente-suspenso-download", is_active=True, billing_status="suspended")
    past_due_org = Organization(name="Cliente Atrasado Download", slug="cliente-atrasado-download", is_active=True, billing_status="past_due")
    platform_admin = User(username="platform-download-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    tenant_admin = User(username="tenant-download-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization=other_org)
    suspended_admin = User(username="tenant-suspended-download-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization=suspended_org)
    db_session.add_all([other_org, third_org, suspended_org, past_due_org, platform_admin, tenant_admin, suspended_admin])
    db_session.commit()

    platform_options = list_agent_deployment_organizations(db=db_session, actor=platform_admin)
    tenant_options = list_agent_deployment_organizations(db=db_session, actor=tenant_admin)
    suspended_tenant_options = list_agent_deployment_organizations(db=db_session, actor=suspended_admin)
    platform_slugs = {organization.slug for organization in platform_options}

    assert platform_slugs >= {"default", "cliente-download", "cliente-atrasado-download"}
    assert "cliente-inativo-download" not in platform_slugs
    assert "cliente-suspenso-download" not in platform_slugs
    assert next(organization for organization in platform_options if organization.slug == "cliente-atrasado-download").billing_status == "past_due"
    assert [organization.slug for organization in tenant_options] == ["cliente-download"]
    assert suspended_tenant_options == []


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


def test_agent_heartbeat_rejects_blank_queue_names():
    with pytest.raises(ValidationError):
        AgentHeartbeatPayload(
            agent_uid="pc-blank-queue",
            queues=[
                {
                    "queue_name": "   ",
                    "driver_name": "KONICA Driver",
                }
            ],
        )


def test_agent_heartbeat_auto_binds_queue_to_known_physical_printer(db_session: Session):
    actor = User(username="agent-bind", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(
        organization_id=1,
        name="KONICA FISICA",
        ip_address="192.168.1.125",
        serial_number="SN-AUTO-123",
        is_color=True,
    )
    db_session.add_all([actor, printer])
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-bind-auto",
            computer_name="PC-BIND",
            queues=[
                {
                    "queue_name": "Konica Financeiro",
                    "driver_name": "KONICA Driver",
                    "port_name": "IP_192.168.1.125",
                    "connection_type": "network",
                    "ip_address": "192.168.1.125",
                    "serial_number": "SN-AUTO-123",
                    "fingerprint": "serial:sn-auto-123",
                }
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    assert response.aliases[0].printer_id == printer.id
    assert "unbound_queues" not in {alert.code for alert in response.health_alerts}


def test_agent_heartbeat_binds_queue_by_serial_case_insensitive(db_session: Session):
    actor = User(username="agent-bind-case", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(
        organization_id=1,
        name="KONICA SERIAL FISICA",
        serial_number="SN-CASE-123",
        is_color=True,
    )
    db_session.add_all([actor, printer])
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-bind-case",
            computer_name="PC-BIND-CASE",
            queues=[
                {
                    "queue_name": "Konica Local",
                    "driver_name": "KONICA Driver",
                    "connection_type": "network",
                    "serial_number": "sn-case-123",
                    "fingerprint": "serial:sn-case-123",
                }
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    assert response.aliases[0].printer_id == printer.id
    assert db_session.query(Printer).count() == 1


def test_agent_heartbeat_updates_printer_ip_when_serial_matches(db_session: Session):
    actor = User(username="agent-bind-serial-ip", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(
        organization_id=1,
        name="KONICA SERIAL IP HEARTBEAT",
        serial_number="SN-HEARTBEAT-IP",
        ip_address="192.168.1.10",
        is_color=True,
    )
    db_session.add_all([actor, printer])
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-bind-serial-ip",
            computer_name="PC-BIND-SERIAL-IP",
            queues=[
                {
                    "queue_name": "Konica Local",
                    "driver_name": "KONICA Driver",
                    "connection_type": "network",
                    "ip_address": "192.168.1.125",
                    "serial_number": "sn-heartbeat-ip",
                    "fingerprint": "serial:sn-heartbeat-ip",
                }
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    updated = db_session.get(Printer, printer.id)
    assert response.aliases[0].printer_id == printer.id
    assert db_session.query(Printer).count() == 1
    assert updated.ip_address == "192.168.1.125"


def test_agent_heartbeat_auto_binds_usb_queue_by_known_device_id(db_session: Session):
    actor = User(username="agent-usb-bind", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="BROTHER USB FISICA", is_color=False)
    known_agent = PrinterAlias(
        organization_id=1,
        printer=printer,
        queue_name="Brother USB",
        connection_type="usb",
        device_id="USBPRINT\\BROTHERDCP-T420W\\7&ABC",
    )
    db_session.add_all([actor, printer, known_agent])
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-usb-bind",
            computer_name="PC-USB",
            queues=[
                {
                    "queue_name": "USER",
                    "driver_name": "Brother Driver",
                    "port_name": "USB001",
                    "connection_type": "usb",
                    "device_id": "USBPRINT\\BROTHERDCP-T420W\\7&ABC",
                    "fingerprint": "usb:pc-usb|usbprint\\brotherdcp-t420w\\7&abc",
                }
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    assert response.aliases[0].printer_id == printer.id
    assert db_session.query(Printer).count() == 1


def test_agent_heartbeat_marks_missing_local_queues_as_stale(db_session: Session):
    actor = User(username="agent-stale-queues", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-stale-queues",
            computer_name="PC-STALE",
            queues=[
                {"queue_name": "KONICA Financeiro", "driver_name": "KONICA Driver", "port_name": "IP_192.168.1.125"},
                {"queue_name": "Brother USB", "driver_name": "Brother Driver", "port_name": "USB001"},
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-stale-queues",
            computer_name="PC-STALE",
            queues=[
                {"queue_name": "Brother USB", "driver_name": "Brother Driver", "port_name": "USB001"},
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    queues = {queue.queue_name: queue for queue in response.aliases}
    assert queues["Brother USB"].is_present is True
    assert queues["KONICA Financeiro"].is_present is False
    assert any(alert.code == "stale_queues" and "KONICA Financeiro" in alert.message for alert in response.health_alerts)


def test_agent_heartbeat_reuses_alias_by_normalized_queue_name(db_session: Session):
    actor = User(username="agent-normalized-queue", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    first = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-normalized-queue",
            computer_name="PC-NORMALIZED",
            queues=[
                {"queue_name": "KONICA Financeiro", "driver_name": "KONICA Driver", "port_name": "IP_192.168.1.125"},
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )
    second = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-normalized-queue",
            computer_name="PC-NORMALIZED",
            queues=[
                {"queue_name": "  konica   financeiro ", "driver_name": "KONICA Driver", "port_name": "IP_192.168.1.125"},
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    assert len(first.aliases) == 1
    assert len(second.aliases) == 1
    assert db_session.query(PrinterAlias).filter(PrinterAlias.organization_id == actor.organization_id).count() == 1
    alias = db_session.query(PrinterAlias).one()
    assert alias.normalized_queue_name == "konica financeiro"
    assert "duplicate_queue_aliases" not in {alert.code for alert in second.health_alerts}


def test_agent_health_alerts_report_duplicate_queue_aliases(db_session: Session):
    now = datetime.now(timezone.utc)
    actor = User(username="agent-duplicate-alias", full_name="Agent", role=UserRole.admin, is_active=True, organization_id=1)
    agent = PrintAgent(organization_id=1, agent_uid="pc-duplicate-alias", computer_name="PC-DUP", last_seen_at=now)
    db_session.add_all([actor, agent])
    db_session.flush()
    db_session.add_all(
        [
            PrinterAlias(
                organization_id=1,
                agent_id=agent.id,
                queue_name="KONICA Financeiro",
                normalized_queue_name="konica financeiro",
                last_seen_at=now,
            ),
            PrinterAlias(
                organization_id=1,
                agent_id=agent.id,
                queue_name="  konica   financeiro ",
                normalized_queue_name="konica financeiro",
                last_seen_at=now,
            ),
        ]
    )
    db_session.commit()

    response = get_agent_detail(agent.id, db=db_session, actor=actor)

    alerts = {alert.code: alert for alert in response.health_alerts}
    assert alerts["duplicate_queue_aliases"].severity == "warning"
    assert "konica" in alerts["duplicate_queue_aliases"].message.lower()


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


def test_outdated_agent_with_disabled_auto_update_is_actionable(db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "agent_latest_version", "0.3.0")
    actor = User(username="agent-update-disabled", full_name="Agent Update Disabled", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-update-disabled",
            version="0.2.0",
            auto_update_enabled=False,
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    alerts = {alert.code: alert for alert in response.health_alerts}
    assert "outdated_version" in alerts
    assert alerts["auto_update_disabled"].severity == "warning"
    assert "Auto-update desativado" in alerts["auto_update_disabled"].message


def test_agent_heartbeat_stores_recent_logs(db_session: Session):
    actor = User(username="agent-logs", full_name="Agent Logs", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-logs",
            computer_name="PC-LOGS",
            logs=[
                {"level": "warning", "message": "Falha temporaria ao consultar SNMP", "source": "snmp"},
                {"level": "strange", "message": "Nivel desconhecido vira info", "source": "diagnostic"},
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )
    detail = get_agent_detail(agent_id=response.id, db=db_session, actor=actor)

    assert [log.message for log in detail.recent_logs] == ["Nivel desconhecido vira info", "Falha temporaria ao consultar SNMP"]
    assert {log.level for log in detail.recent_logs} == {"info", "warning"}
    assert detail.recent_logs[0].source == "diagnostic"


def test_agent_detail_recent_jobs_include_policy_context(db_session: Session):
    actor = User(username="agent-policy-job-admin", full_name="Agent Policy Job", role=UserRole.admin, is_active=True, organization_id=1)
    user = User(username="agent-policy-job-user", full_name="Agent Policy User", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA POLICY JOB", is_color=True)
    db_session.add_all([actor, user, printer])
    db_session.commit()
    agent = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-policy-job", computer_name="PC-POLICY-JOB"),
        request=_request(),
        db=db_session,
        actor=actor,
    )
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        agent_id=agent.id,
        pages=2,
        is_color=True,
        cost=0.50,
        status=JobStatus.blocked,
        document_name="Contrato.pdf",
        policy_name="Bloquear colorido",
        policy_action="block",
    )
    db_session.add(job)
    db_session.commit()

    detail = get_agent_detail(agent_id=agent.id, db=db_session, actor=actor)

    assert detail.recent_jobs[0].document_name == "Contrato.pdf"
    assert detail.recent_jobs[0].policy_name == "Bloquear colorido"
    assert detail.recent_jobs[0].policy_action == "block"


def test_agent_error_logs_create_operational_alert(db_session: Session):
    actor = User(username="agent-error-log-alert", full_name="Agent Error Log", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(
            agent_uid="pc-error-log-alert",
            computer_name="PC-ERROR-LOG",
            logs=[
                {"level": "error", "message": "Falha ao consultar fila local", "source": "spool"},
            ],
        ),
        request=_request(),
        db=db_session,
        actor=actor,
    )
    listed_agent = next(agent for agent in list_agents(db=db_session, actor=actor) if agent.id == response.id)

    assert "last_error" not in {alert.code for alert in response.health_alerts}
    assert any(alert.code == "recent_error_logs" and "Falha ao consultar fila local" in alert.message for alert in response.health_alerts)
    assert any(alert.code == "recent_error_logs" for alert in listed_agent.health_alerts)


def test_agent_logs_are_pruned_per_agent(db_session: Session):
    actor = User(username="agent-prune", full_name="Agent Prune", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()
    response = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="pc-prune", computer_name="PC-PRUNE"),
        request=_request(),
        db=db_session,
        actor=actor,
    )

    for index in range(205):
        agent_heartbeat(
            payload=AgentHeartbeatPayload(
                agent_uid="pc-prune",
                computer_name="PC-PRUNE",
                logs=[{"level": "info", "message": f"evento {index:03d}", "source": "test"}],
            ),
            request=_request(),
            db=db_session,
            actor=actor,
        )

    assert db_session.query(AgentLog).filter(AgentLog.agent_id == response.id).count() == 200
    detail = get_agent_detail(agent_id=response.id, db=db_session, actor=actor)
    assert len(detail.recent_logs) == 50
    assert detail.recent_logs[0].message == "evento 204"


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


def test_list_agents_reports_stale_running_queue_actions(db_session: Session):
    actor = User(username="agent-stale-action-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA STALE ACTION", ip_address="192.168.1.130", is_color=True)
    db_session.add_all([actor, printer])
    db_session.commit()
    agent = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-stale-action", computer_name="PC-STALE-ACTION"),
        request=_request("10.0.0.34"),
        db=db_session,
        actor=actor,
    )
    action = create_queue_action(
        agent_id=agent.id,
        payload=AgentQueueActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="KONICA_STALE_ACTION",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            ip_address="192.168.1.130",
        ),
        db=db_session,
        actor=actor,
    )
    poll_queue_actions(agent_uid=agent.agent_uid, db=db_session, actor=actor)
    persisted_action = db_session.get(type(action), action.id)
    persisted_action.dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db_session.commit()

    rows = list_agents(db=db_session, actor=actor)
    stale_agent = next(row for row in rows if row.agent_uid == agent.agent_uid)

    assert any(
        alert.code == "stale_queue_actions" and "KONICA_STALE_ACTION" in alert.message
        for alert in stale_agent.health_alerts
    )


def test_poll_queue_actions_redispatches_stale_running_actions(db_session: Session):
    actor = User(username="agent-redispatch-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA REDISPATCH", ip_address="192.168.1.131", is_color=True)
    db_session.add_all([actor, printer])
    db_session.commit()
    agent = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-redispatch", computer_name="PC-REDISPATCH"),
        request=_request("10.0.0.35"),
        db=db_session,
        actor=actor,
    )
    action = create_queue_action(
        agent_id=agent.id,
        payload=AgentQueueActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="KONICA_REDISPATCH",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            ip_address="192.168.1.131",
        ),
        db=db_session,
        actor=actor,
    )
    first_dispatch = poll_queue_actions(agent_uid=agent.agent_uid, db=db_session, actor=actor)
    old_dispatched_at = first_dispatch[0].dispatched_at
    persisted_action = db_session.get(type(action), action.id)
    persisted_action.dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db_session.commit()

    redispatched = poll_queue_actions(agent_uid=agent.agent_uid, db=db_session, actor=actor)

    assert [item.id for item in redispatched] == [action.id]
    assert redispatched[0].status == AgentQueueActionStatus.running
    assert redispatched[0].dispatched_at is not None
    assert old_dispatched_at is not None
    assert redispatched[0].dispatched_at > old_dispatched_at
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "agent_queue_action_dispatched", AuditLog.entity_id == action.id)
        .order_by(AuditLog.id)
        .all()
    )
    assert [audit.log_metadata["redispatch"] for audit in audits] == [False, True]
    assert audits[0].log_metadata["previous_status"] == "pending"
    assert audits[1].log_metadata["previous_status"] == "running"
    assert audits[1].log_metadata["previous_dispatched_at"] is not None


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


def test_remote_queue_action_rejects_blank_queue_name():
    with pytest.raises(ValidationError):
        AgentQueueActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="   ",
            driver_name="KONICA Driver",
            ip_address="192.168.1.125",
        )


def test_queue_action_result_requires_running_status(db_session: Session):
    actor = User(username="queue-state-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA STATE", ip_address="192.168.1.129", is_color=True)
    db_session.add_all([actor, printer])
    db_session.commit()
    agent = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-queue-state", computer_name="PC-STATE"),
        request=_request("10.0.0.33"),
        db=db_session,
        actor=actor,
    )
    action = create_queue_action(
        agent_id=agent.id,
        payload=AgentQueueActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="KONICA_STATE",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            ip_address="192.168.1.129",
        ),
        db=db_session,
        actor=actor,
    )

    with pytest.raises(HTTPException) as pending_exc:
        finish_queue_action(
            action_id=action.id,
            payload=AgentQueueActionResult(status=AgentQueueActionStatus.succeeded, result_message="antes do despacho"),
            db=db_session,
            actor=actor,
        )
    assert pending_exc.value.status_code == 409
    db_session.rollback()

    poll_queue_actions(agent_uid=agent.agent_uid, db=db_session, actor=actor)
    finish_queue_action(
        action_id=action.id,
        payload=AgentQueueActionResult(status=AgentQueueActionStatus.succeeded, result_message="concluida"),
        db=db_session,
        actor=actor,
    )

    with pytest.raises(HTTPException) as completed_exc:
        finish_queue_action(
            action_id=action.id,
            payload=AgentQueueActionResult(status=AgentQueueActionStatus.failed, result_message="sobrescrever"),
            db=db_session,
            actor=actor,
        )
    assert completed_exc.value.status_code == 409
    db_session.rollback()
    persisted = db_session.get(type(action), action.id)
    assert persisted.status == AgentQueueActionStatus.succeeded
    assert persisted.result_message == "concluida"


def test_restore_queue_action_rebinds_physical_printer(db_session: Session):
    actor = User(username="queue-restore-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA RESTAURAR", ip_address="192.168.1.126", is_color=True)
    db_session.add_all([actor, printer])
    db_session.commit()
    agent = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-restore-1", computer_name="PC-RESTORE"),
        request=_request("10.0.0.6"),
        db=db_session,
        actor=actor,
    )

    action = create_queue_action(
        agent_id=agent.id,
        payload=AgentQueueActionCreate(
            action_type=AgentQueueActionType.restore_queue,
            queue_name="KONICA_RESTAURADA",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            port_name="IP_192.168.1.126",
        ),
        db=db_session,
        actor=actor,
    )

    pending = poll_queue_actions(agent_uid="agent-restore-1", db=db_session, actor=actor)
    assert [item.action_type for item in pending] == [AgentQueueActionType.restore_queue]

    finish_queue_action(
        action_id=action.id,
        payload=AgentQueueActionResult(status=AgentQueueActionStatus.succeeded, result_message="Fila restaurada"),
        db=db_session,
        actor=actor,
    )

    alias = db_session.query(PrinterAlias).filter(PrinterAlias.queue_name == "KONICA_RESTAURADA").one()
    assert alias.printer_id == printer.id
    assert alias.driver_name == "KONICA Driver"
    assert alias.port_name == "IP_192.168.1.126"


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


def test_agent_queue_action_result_requires_matching_agent_uid_for_agent_role(db_session: Session):
    admin = User(username="queue-result-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    agent_user = User(username="queue-result-agent", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_RESULT", ip_address="192.168.1.128", is_color=True)
    db_session.add_all([admin, agent_user, printer])
    db_session.commit()
    agent_a = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-result-a", computer_name="PC-A"),
        request=_request("10.0.0.31"),
        db=db_session,
        actor=admin,
    )
    agent_b = agent_heartbeat(
        payload=AgentHeartbeatPayload(agent_uid="agent-result-b", computer_name="PC-B"),
        request=_request("10.0.0.32"),
        db=db_session,
        actor=admin,
    )
    action = create_queue_action(
        agent_id=agent_b.id,
        payload=AgentQueueActionCreate(
            action_type=AgentQueueActionType.create_queue,
            queue_name="KONICA_RESULT",
            printer_id=printer.id,
            driver_name="KONICA Driver",
            ip_address="192.168.1.128",
        ),
        db=db_session,
        actor=admin,
    )
    poll_queue_actions(agent_uid=agent_b.agent_uid, db=db_session, actor=agent_user)

    with pytest.raises(HTTPException) as exc:
        finish_queue_action(
            action_id=action.id,
            payload=AgentQueueActionResult(status=AgentQueueActionStatus.succeeded, result_message="errado", agent_uid=agent_a.agent_uid),
            db=db_session,
            actor=agent_user,
        )

    assert exc.value.status_code == 403
    db_session.rollback()
    unchanged = db_session.get(type(action), action.id)
    assert unchanged.status == AgentQueueActionStatus.running

    finished = finish_queue_action(
        action_id=action.id,
        payload=AgentQueueActionResult(status=AgentQueueActionStatus.succeeded, result_message="correto", agent_uid=agent_b.agent_uid),
        db=db_session,
        actor=agent_user,
    )

    assert finished.status == AgentQueueActionStatus.succeeded
    assert finished.result_message == "correto"


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
