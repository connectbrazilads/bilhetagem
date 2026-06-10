from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.api.routes.jobs import get_agent_web_prints, web_print_endpoint
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.models.print_job import PrintJob, JobStatus
from app.models.quota import Quota
from app.services.settings_service import update_system_settings
from app.services.print_job_service import register_print_job
from app.schemas.job import PrintJobCreate
from app.api.routes.settings import (
    get_general_settings,
    update_general_settings,
    update_monthly_report_email_settings_endpoint,
)
from app.models.audit_log import AuditLog
from app.schemas.settings import GeneralSettings, MonthlyReportEmailSettings


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

    # 2. PUT updated settings
    updated_payload = GeneralSettings(
        default_monthly_quota=200,
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

    # 3. GET to verify persistence
    res_verified = get_general_settings(db=db_session, actor=actor)
    assert res_verified.blocking_enabled is False
    assert res_verified.show_balance is False
    assert res_verified.web_print_enabled is False


def test_settings_updates_are_audited(db_session: Session):
    actor = User(username="admin-settings-audit", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    update_general_settings(
        payload=GeneralSettings(
            default_monthly_quota=250,
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
    assert log.log_metadata["changes"]["blocking_enabled"] == {"before": True, "after": False}
    assert log.log_metadata["changes"]["safe_release_enabled"] == {"before": True, "after": False}
    assert log.log_metadata["changes"]["web_print_enabled"] == {"before": True, "after": False}


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


def test_web_print_module_can_be_disabled(db_session: Session):
    actor = User(username="admin-webprint-settings", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    update_system_settings(db_session, {"web_print_enabled": False}, actor.organization_id)

    with pytest.raises(HTTPException) as exc:
        web_print_endpoint(file=None, printer_id=999, is_color=False, db=db_session, current_user=actor)
    assert exc.value.status_code == 403
    assert get_agent_web_prints(db=db_session, current_user=actor) == []


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
