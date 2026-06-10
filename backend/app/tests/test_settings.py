from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.api.routes.jobs import create_job, get_agent_web_prints, web_print_endpoint
from app.models.organization import Organization
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.models.print_job import PrintJob, JobStatus
from app.models.quota import Quota
from app.models.system_setting import SystemSetting
from app.services.settings_service import update_system_settings
from app.services.print_job_service import register_print_job
from app.schemas.job import PrintJobCreate
from app.api.routes.settings import (
    get_agent_runtime_settings,
    get_general_settings,
    get_ldap_settings_endpoint,
    get_operational_settings,
    test_ldap_endpoint as ldap_test_endpoint,
    sync_ldap_endpoint,
    update_general_settings,
    update_ldap_settings_endpoint,
    update_monthly_report_email_settings_endpoint,
)
from app.api.routes.printers import create_printer_endpoint, update_printer_endpoint
from app.models.audit_log import AuditLog
from app.schemas.printer import PrinterCreate, PrinterUpdate
from app.schemas.settings import GeneralSettings, LDAPSettings, MonthlyReportEmailSettings


def test_general_settings_api(db_session: Session):
    actor = User(username="admin-settings", full_name="Admin", role=UserRole.admin, is_active=True)
    db_session.add(actor)
    db_session.commit()

    # 1. GET initial settings (should return defaults)
    res = get_general_settings(db=db_session, actor=actor)
    assert res.blocking_enabled is True
    assert res.show_balance is True
    assert res.web_print_enabled is True
    assert res.default_monthly_quota == 500
    assert res.default_printer_cost_mono == 0.05
    assert res.default_printer_cost_color == 0.25

    # 2. PUT updated settings
    updated_payload = GeneralSettings(
        default_monthly_quota=200,
        default_printer_cost_mono=0.07,
        default_printer_cost_color=0.32,
        auto_create_users=False,
        blocking_enabled=False,
        show_balance=False,
        safe_release_enabled=True,
        web_print_enabled=False,
    )
    res_updated = update_general_settings(payload=updated_payload, db=db_session, actor=actor)
    assert res_updated.blocking_enabled is False
    assert res_updated.show_balance is False
    assert res_updated.web_print_enabled is False
    assert res_updated.default_monthly_quota == 200
    assert res_updated.default_printer_cost_mono == 0.07
    assert res_updated.default_printer_cost_color == 0.32

    # 3. GET to verify persistence
    res_verified = get_general_settings(db=db_session, actor=actor)
    assert res_verified.blocking_enabled is False
    assert res_verified.show_balance is False
    assert res_verified.web_print_enabled is False
    assert res_verified.default_printer_cost_mono == 0.07
    assert res_verified.default_printer_cost_color == 0.32


def test_general_settings_fall_back_when_stored_values_are_invalid(db_session: Session):
    actor = User(username="admin-invalid-settings", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.add_all(
        [
            SystemSetting(organization_id=1, key="default_monthly_quota", value="-10"),
            SystemSetting(organization_id=1, key="default_printer_cost_mono", value="abc"),
            SystemSetting(organization_id=1, key="default_printer_cost_color", value="-0.25"),
            SystemSetting(organization_id=1, key="blocking_enabled", value="talvez"),
            SystemSetting(organization_id=1, key="show_balance", value="nao"),
            SystemSetting(organization_id=1, key="web_print_enabled", value="sim"),
        ]
    )
    db_session.commit()

    settings = get_general_settings(db=db_session, actor=actor)

    assert settings.default_monthly_quota == 500
    assert settings.default_printer_cost_mono == 0.05
    assert settings.default_printer_cost_color == 0.25
    assert settings.blocking_enabled is True
    assert settings.show_balance is False
    assert settings.web_print_enabled is True


def test_ldap_settings_are_saved_per_organization_without_returning_password(db_session: Session):
    actor = User(username="admin-ldap-settings", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    updated = update_ldap_settings_endpoint(
        payload=LDAPSettings(
            server="ldap://ad.empresa.local:389",
            bind_dn="cn=admin,dc=empresa,dc=local",
            bind_password="secret",
            search_base="dc=empresa,dc=local",
        ),
        db=db_session,
        actor=actor,
    )

    loaded = get_ldap_settings_endpoint(db=db_session, actor=actor)
    audit = db_session.query(AuditLog).filter(AuditLog.action == "ldap_settings_updated").one()
    password_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.organization_id == actor.organization_id, SystemSetting.key == "ldap_bind_password")
        .one()
    )
    assert updated.server == "ldap://ad.empresa.local:389"
    assert updated.has_bind_password is True
    assert loaded.bind_dn == "cn=admin,dc=empresa,dc=local"
    assert loaded.has_bind_password is True
    assert password_row.value == "secret"
    assert "bind_password" not in loaded.model_dump()
    assert "secret" not in str(audit.log_metadata)
    assert "ldap_bind_password" not in str(audit.log_metadata)


def test_ldap_test_endpoint_uses_saved_password_when_payload_omits_it(db_session: Session, monkeypatch):
    actor = User(username="admin-ldap-test", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()
    update_ldap_settings_endpoint(
        payload=LDAPSettings(
            server="ldap://ad.empresa.local:389",
            bind_dn="cn=admin,dc=empresa,dc=local",
            bind_password="secret",
            search_base="dc=empresa,dc=local",
        ),
        db=db_session,
        actor=actor,
    )
    calls = []

    def fake_test_connection(server: str, bind_dn: str, bind_password: str) -> bool:
        calls.append((server, bind_dn, bind_password))
        return True

    monkeypatch.setattr("app.api.routes.settings.test_ldap_connection", fake_test_connection)

    response = ldap_test_endpoint(payload=LDAPSettings(), db=db_session, actor=actor)

    assert response["success"] is True
    assert calls == [("ldap://ad.empresa.local:389", "cn=admin,dc=empresa,dc=local", "secret")]


def test_ldap_sync_endpoint_uses_saved_settings_when_payload_omits_them(db_session: Session, monkeypatch):
    actor = User(username="admin-ldap-sync-settings", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()
    update_ldap_settings_endpoint(
        payload=LDAPSettings(
            server="ldap://ad.empresa.local:389",
            bind_dn="cn=admin,dc=empresa,dc=local",
            bind_password="secret",
            search_base="dc=empresa,dc=local",
        ),
        db=db_session,
        actor=actor,
    )
    calls = []

    def fake_sync_users(db: Session, server: str, bind_dn: str, bind_password: str, search_base: str, organization_id: int | None = None) -> dict:
        calls.append((server, bind_dn, bind_password, search_base, organization_id))
        return {"success": True, "total_synced": 0, "new_users": 0, "updated_users": 0, "skipped_users": 0}

    monkeypatch.setattr("app.api.routes.settings.sync_ldap_users", fake_sync_users)

    response = sync_ldap_endpoint(payload=LDAPSettings(), db=db_session, actor=actor)

    assert response["success"] is True
    assert calls == [("ldap://ad.empresa.local:389", "cn=admin,dc=empresa,dc=local", "secret", "dc=empresa,dc=local", 1)]


def test_settings_updates_are_audited(db_session: Session):
    actor = User(username="admin-settings-audit", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    update_general_settings(
        payload=GeneralSettings(
            default_monthly_quota=250,
            default_printer_cost_mono=0.08,
            default_printer_cost_color=0.35,
            auto_create_users=True,
            blocking_enabled=False,
            show_balance=True,
            safe_release_enabled=False,
            web_print_enabled=False,
        ),
        db=db_session,
        actor=actor,
    )

    log = db_session.query(AuditLog).filter(AuditLog.action == "settings_updated").one()
    assert log.organization_id == actor.organization_id
    assert log.actor_user_id == actor.id
    assert log.log_metadata["changes"]["default_monthly_quota"] == {"before": 500, "after": 250}
    assert log.log_metadata["changes"]["default_printer_cost_mono"] == {"before": 0.05, "after": 0.08}
    assert log.log_metadata["changes"]["default_printer_cost_color"] == {"before": 0.25, "after": 0.35}
    assert log.log_metadata["changes"]["blocking_enabled"] == {"before": True, "after": False}
    assert log.log_metadata["changes"]["safe_release_enabled"] == {"before": True, "after": False}
    assert log.log_metadata["changes"]["web_print_enabled"] == {"before": True, "after": False}


def test_manager_can_read_operational_settings(db_session: Session):
    manager = User(username="manager-settings", full_name="Manager", role=UserRole.manager, is_active=True, organization_id=1)
    db_session.add(manager)
    db_session.commit()
    update_system_settings(db_session, {"safe_release_enabled": False}, manager.organization_id)

    settings = get_operational_settings(db=db_session, actor=manager)

    assert settings.safe_release_enabled is False


def test_agent_runtime_settings_returns_minimal_capture_flags(db_session: Session):
    agent = User(username="agent-runtime-settings", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    db_session.add(agent)
    db_session.commit()
    update_system_settings(
        db_session,
        {
            "default_monthly_quota": 200,
            "default_printer_cost_mono": 0.09,
            "blocking_enabled": False,
            "safe_release_enabled": False,
        },
        agent.organization_id,
    )

    settings = get_agent_runtime_settings(db=db_session, actor=agent)

    assert settings.safe_release_enabled is False
    assert settings.model_dump() == {"safe_release_enabled": False}


def test_auto_created_printer_uses_organization_default_costs(db_session: Session):
    actor = User(username="admin-cost-settings", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()
    update_system_settings(
        db_session,
        {
            "default_printer_cost_mono": 0.09,
            "default_printer_cost_color": 0.42,
            "safe_release_enabled": False,
        },
        actor.organization_id,
    )

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="usuario-custos",
            printer_name="IMPRESSORA_AUTO_CUSTOS",
            pages=10,
            is_color=True,
            submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        ),
        organization_id=actor.organization_id,
    )

    printer = db_session.query(Printer).filter(Printer.name == "IMPRESSORA_AUTO_CUSTOS").one()
    job = db_session.query(PrintJob).filter(PrintJob.id == decision.job_id).one()
    assert printer.cost_mono == 0.09
    assert printer.cost_color == 0.42
    assert job.cost == 4.2


def test_manual_printer_creation_uses_organization_default_costs(db_session: Session):
    actor = User(username="admin-manual-costs", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()
    update_system_settings(
        db_session,
        {
            "default_printer_cost_mono": 0.11,
            "default_printer_cost_color": 0.48,
        },
        actor.organization_id,
    )

    printer = create_printer_endpoint(
        PrinterCreate(name="IMPRESSORA_MANUAL_CUSTOS", is_color=True),
        db_session,
        actor,
    )

    assert printer.cost_mono == 0.11
    assert printer.cost_color == 0.48


def test_manual_printer_creation_keeps_explicit_costs(db_session: Session):
    actor = User(username="admin-explicit-costs", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()
    update_system_settings(
        db_session,
        {
            "default_printer_cost_mono": 0.11,
            "default_printer_cost_color": 0.48,
        },
        actor.organization_id,
    )

    printer = create_printer_endpoint(
        PrinterCreate(name="IMPRESSORA_MANUAL_EXPLICITA", is_color=True, cost_mono=0.06, cost_color=0.31),
        db_session,
        actor,
    )

    assert printer.cost_mono == 0.06
    assert printer.cost_color == 0.31


def test_manual_printer_creation_respects_contracted_limit(db_session: Session):
    organization = db_session.query(Organization).filter(Organization.id == 1).one()
    organization.contracted_printer_limit = 1
    actor = User(username="admin-printer-limit", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    active_printer = Printer(organization_id=1, name="IMPRESSORA_EXISTENTE_LIMITE", is_color=False, is_active=True)
    db_session.add_all([actor, active_printer])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        create_printer_endpoint(
            PrinterCreate(name="IMPRESSORA_ACIMA_LIMITE", is_color=False),
            db_session,
            actor,
        )

    assert exc.value.status_code == 409
    assert "Limite contratado de impressoras atingido" in exc.value.detail

    active_printer.is_active = False
    db_session.commit()
    printer = create_printer_endpoint(
        PrinterCreate(name="IMPRESSORA_DENTRO_LIMITE", is_color=False),
        db_session,
        actor,
    )

    assert printer.name == "IMPRESSORA_DENTRO_LIMITE"


def test_auto_printer_creation_respects_contracted_limit(db_session: Session):
    organization = db_session.query(Organization).filter(Organization.id == 1).one()
    organization.contracted_printer_limit = 1
    agent = User(username="agent-printer-limit", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    active_printer = Printer(organization_id=1, name="IMPRESSORA_AUTO_EXISTENTE_LIMITE", is_color=False, is_active=True)
    db_session.add_all([agent, active_printer])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        create_job(
            PrintJobCreate(
                username="usuario-limite-printer",
                printer_name="IMPRESSORA_AUTO_ACIMA_LIMITE",
                pages=1,
                is_color=False,
                submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            ),
            db=db_session,
            current_user=agent,
        )

    assert exc.value.status_code == 409
    assert "Limite contratado de impressoras atingido" in exc.value.detail
    assert db_session.query(Printer).filter(Printer.name == "IMPRESSORA_AUTO_ACIMA_LIMITE").first() is None


def test_reactivating_printer_respects_contracted_limit(db_session: Session):
    organization = db_session.query(Organization).filter(Organization.id == 1).one()
    organization.contracted_printer_limit = 1
    actor = User(username="admin-reactivate-limit", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    active_printer = Printer(organization_id=1, name="IMPRESSORA_ATIVA_LIMITE", is_color=False, is_active=True)
    inactive_printer = Printer(organization_id=1, name="IMPRESSORA_INATIVA_LIMITE", is_color=False, is_active=False)
    db_session.add_all([actor, active_printer, inactive_printer])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_printer_endpoint(
            inactive_printer.id,
            PrinterUpdate(is_active=True),
            db_session,
            actor,
        )

    assert exc.value.status_code == 409
    assert "Limite contratado de impressoras atingido" in exc.value.detail
    db_session.refresh(inactive_printer)
    assert inactive_printer.is_active is False


def test_monthly_report_email_settings_updates_are_audited(db_session: Session):
    actor = User(username="admin-email-audit", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    update_monthly_report_email_settings_endpoint(
        payload=MonthlyReportEmailSettings(
            enabled=True,
            recipients="financeiro@empresa.com",
            day_of_month=5,
            include_pdf=True,
            include_xlsx=False,
        ),
        db=db_session,
        actor=actor,
    )

    log = db_session.query(AuditLog).filter(AuditLog.action == "monthly_report_email_settings_updated").one()
    assert log.organization_id == actor.organization_id
    assert log.actor_user_id == actor.id
    assert log.log_metadata["changes"]["enabled"] == {"before": False, "after": True}
    assert log.log_metadata["changes"]["recipients"]["after"] == "financeiro@empresa.com"
    assert log.log_metadata["changes"]["day_of_month"] == {"before": 1, "after": 5}
    assert log.log_metadata["changes"]["include_xlsx"] == {"before": True, "after": False}


def test_monthly_report_email_settings_reject_invalid_recipients_without_audit(db_session: Session):
    actor = User(username="admin-email-invalid", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_monthly_report_email_settings_endpoint(
            payload=MonthlyReportEmailSettings(
                enabled=True,
                recipients="financeiro@empresa.com; email-invalido",
                day_of_month=5,
                include_pdf=True,
                include_xlsx=True,
            ),
            db=db_session,
            actor=actor,
        )

    assert exc.value.status_code == 400
    assert "Destinatario invalido" in exc.value.detail
    assert db_session.query(SystemSetting).filter(SystemSetting.key == "monthly_report_email_recipients").count() == 0
    assert db_session.query(AuditLog).filter(AuditLog.action == "monthly_report_email_settings_updated").count() == 0


def test_monthly_report_email_settings_fall_back_when_stored_values_are_invalid(db_session: Session):
    actor = User(username="admin-invalid-email-settings", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.add_all(
        [
            SystemSetting(organization_id=1, key="monthly_report_email_enabled", value="talvez"),
            SystemSetting(organization_id=1, key="monthly_report_email_recipients", value="financeiro@empresa.com"),
            SystemSetting(organization_id=1, key="monthly_report_email_day_of_month", value="31"),
            SystemSetting(organization_id=1, key="monthly_report_email_include_pdf", value="sim"),
            SystemSetting(organization_id=1, key="monthly_report_email_include_xlsx", value="nao"),
        ]
    )
    db_session.commit()

    settings = update_monthly_report_email_settings_endpoint(
        payload=MonthlyReportEmailSettings(
            enabled=True,
            recipients="financeiro@empresa.com",
            day_of_month=5,
            include_pdf=True,
            include_xlsx=False,
        ),
        db=db_session,
        actor=actor,
    )

    assert settings.enabled is True
    assert settings.day_of_month == 5
    assert settings.include_pdf is True
    assert settings.include_xlsx is False


def test_web_print_module_can_be_disabled(db_session: Session):
    actor = User(username="admin-webprint-settings", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    update_system_settings(db_session, {"web_print_enabled": False}, actor.organization_id)

    with pytest.raises(HTTPException) as exc:
        web_print_endpoint(file=None, printer_id=999, is_color=False, db=db_session, current_user=actor)
    assert exc.value.status_code == 403
    assert get_agent_web_prints(db=db_session, current_user=actor) == []


def test_disabling_safe_release_authorizes_pending_jobs_and_writes_audit(db_session: Session):
    user = User(username="followme-user", full_name="FollowMe User", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA FOLLOWME", is_color=True)
    db_session.add_all([user, printer])
    db_session.flush()
    quota = Quota(
        organization_id=1,
        user_id=user.id,
        year=2026,
        month=6,
        monthly_limit=100,
        used_pages=0,
        monthly_balance=50.0,
        used_balance=0.0,
    )
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        pages=4,
        is_color=True,
        cost=1.0,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add_all([quota, job])
    db_session.commit()

    update_system_settings(db_session, {"safe_release_enabled": False}, organization_id=1)

    db_session.refresh(job)
    db_session.refresh(quota)
    audit = db_session.query(AuditLog).filter(AuditLog.action == "pending_jobs_auto_released").one()
    assert job.status == JobStatus.authorized
    assert job.reason == "Liberado automaticamente ao desativar Follow-Me"
    assert quota.used_pages == 4
    assert quota.used_balance == 1.0
    assert audit.organization_id == 1
    assert audit.actor_user_id is None
    assert audit.log_metadata == {"jobs": 1, "pages": 4, "cost": 1.0, "reason": "safe_release_disabled"}


def test_saving_settings_with_safe_release_already_disabled_does_not_flush_pending_jobs(db_session: Session):
    user = User(username="policy-pending-user", full_name="Policy Pending", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA POLICY PENDING", is_color=True)
    db_session.add_all([user, printer])
    db_session.flush()
    quota = Quota(
        organization_id=1,
        user_id=user.id,
        year=2026,
        month=6,
        monthly_limit=100,
        used_pages=0,
        monthly_balance=50.0,
        used_balance=0.0,
    )
    db_session.add(quota)
    db_session.commit()
    update_system_settings(db_session, {"safe_release_enabled": False}, organization_id=1)

    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        pages=6,
        is_color=True,
        cost=1.5,
        status=JobStatus.pending_release,
        reason="Liberacao exigida por politica",
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    update_system_settings(
        db_session,
        {
            "default_monthly_quota": 600,
            "auto_create_users": True,
            "blocking_enabled": True,
            "show_balance": True,
            "safe_release_enabled": False,
            "web_print_enabled": True,
        },
        organization_id=1,
    )

    db_session.refresh(job)
    db_session.refresh(quota)
    assert job.status == JobStatus.pending_release
    assert job.reason == "Liberacao exigida por politica"
    assert quota.used_pages == 0
    assert quota.used_balance == 0.0
    assert db_session.query(AuditLog).filter(AuditLog.action == "pending_jobs_auto_released").count() == 0


def test_general_settings_auto_release_audit_uses_admin_actor(db_session: Session):
    actor = User(username="followme-admin", full_name="FollowMe Admin", role=UserRole.admin, is_active=True, organization_id=1)
    user = User(username="followme-actor-user", full_name="FollowMe Actor User", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA FOLLOWME ACTOR", is_color=True)
    db_session.add_all([actor, user, printer])
    db_session.flush()
    db_session.add_all(
        [
            Quota(
                organization_id=1,
                user_id=user.id,
                year=2026,
                month=6,
                monthly_limit=100,
                used_pages=0,
                monthly_balance=50.0,
                used_balance=0.0,
            ),
            PrintJob(
                organization_id=1,
                user_id=user.id,
                printer_id=printer.id,
                pages=2,
                is_color=False,
                cost=0.10,
                status=JobStatus.pending_release,
                submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    update_general_settings(
        payload=GeneralSettings(
            default_monthly_quota=500,
            default_printer_cost_mono=0.05,
            default_printer_cost_color=0.25,
            auto_create_users=True,
            blocking_enabled=True,
            show_balance=True,
            safe_release_enabled=False,
            web_print_enabled=True,
        ),
        db=db_session,
        actor=actor,
    )

    auto_release_audit = db_session.query(AuditLog).filter(AuditLog.action == "pending_jobs_auto_released").one()
    settings_audit = db_session.query(AuditLog).filter(AuditLog.action == "settings_updated").one()
    assert auto_release_audit.actor_user_id == actor.id
    assert settings_audit.actor_user_id == actor.id
    assert auto_release_audit.log_metadata["jobs"] == 1


def test_blocking_disabled_behavior(db_session: Session):
    # Create user, printer, and quota with 0 remaining pages
    user = User(username="poor_user", full_name="Poor User", role=UserRole.user)
    db_session.add(user)
    db_session.flush()

    # Quota has monthly limit = 10, used pages = 10 (0 remaining!)
    quota = Quota(
        user_id=user.id,
        year=2026,
        month=6,
        monthly_limit=10,
        used_pages=10,
        monthly_balance=5.0,
        used_balance=5.0
    )
    db_session.add(quota)

    printer = Printer(name="EcoPrint", is_color=False, cost_mono=0.10, cost_color=0.50)
    db_session.add(printer)
    db_session.commit()

    # 1. Register a print job with blocking ENABLED (default)
    # This should be blocked
    decision_blocked = register_print_job(
        db_session,
        PrintJobCreate(
            username="poor_user",
            printer_name="EcoPrint",
            pages=5,
            is_color=False,
            submitted_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
        )
    )
    assert decision_blocked.authorized is False
    assert decision_blocked.status == JobStatus.blocked

    # 2. Set blocking_enabled = False in settings
    from app.services.settings_service import update_system_settings
    update_system_settings(db_session, {"blocking_enabled": False})

    # 3. Register a print job with blocking DISABLED
    # This should be authorized despite 0 remaining pages/balance!
    decision_allowed = register_print_job(
        db_session,
        PrintJobCreate(
            username="poor_user",
            printer_name="EcoPrint",
            pages=5,
            is_color=False,
            submitted_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
        )
    )
    assert decision_allowed.authorized is True
    # since safe_release_enabled defaults to True, it should be pending_release
    assert decision_allowed.status == JobStatus.pending_release
