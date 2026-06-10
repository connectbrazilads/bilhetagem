from datetime import datetime, timezone

from fastapi import HTTPException
import pytest

from app.api.routes.jobs import cancel_job, get_agent_actions, release_job
from app.models.audit_log import AuditLog
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.quota import Quota
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate
from app.services.print_job_service import register_print_job


def test_authorizes_and_debits_when_quota_has_balance(db_session, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "safe_release_enabled", False)

    user = User(username="joao", full_name="João", role=UserRole.user)
    printer = Printer(name="HP Financeiro", is_color=True)
    db_session.add_all([user, printer])
    db_session.flush()
    db_session.add(Quota(user_id=user.id, year=2026, month=6, monthly_limit=500, used_pages=420))
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="joao",
            printer_name="HP Financeiro",
            pages=20,
            is_color=True,
            submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        ),
    )

    assert decision.authorized is True
    assert decision.remaining_pages == 60


def test_blocks_and_keeps_balance_when_quota_is_insufficient(db_session):
    user = User(username="maria", full_name="Maria", role=UserRole.user)
    printer = Printer(name="Ricoh RH", is_color=False)
    db_session.add_all([user, printer])
    db_session.flush()
    db_session.add(Quota(user_id=user.id, year=2026, month=6, monthly_limit=100, used_pages=95))
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="maria",
            printer_name="Ricoh RH",
            pages=10,
            is_color=False,
            submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        ),
    )

    quota = db_session.query(Quota).filter(Quota.user_id == user.id).one()
    assert decision.authorized is False
    assert decision.remaining_pages == 5
    assert quota.used_pages == 95


def test_auto_creates_normalized_windows_user(db_session):
    printer = Printer(name="Canon Recepcao", is_color=False)
    db_session.add(printer)
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="EMPRESA\\MARIA.SILVA",
            printer_name="Canon Recepcao",
            pages=1,
            is_color=False,
            submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        ),
    )

    user = db_session.query(User).filter(User.username == "maria.silva").one()
    assert decision.authorized is True
    assert user.full_name == "maria.silva"


def test_auto_created_windows_user_replaces_spaces_with_underscores(db_session):
    printer = Printer(name="Canon Diretoria", is_color=False)
    db_session.add(printer)
    db_session.commit()

    register_print_job(
        db_session,
        PrintJobCreate(
            username="EMPRESA\\DIEGO   LCD",
            printer_name="Canon Diretoria",
            pages=1,
            is_color=False,
            submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        ),
    )

    user = db_session.query(User).filter(User.username == "diego_lcd").one()
    assert user.full_name == "diego_lcd"


def test_reuses_existing_spool_job(db_session):
    user = User(username="ana", full_name="Ana", role=UserRole.user)
    printer = Printer(name="Ricoh Fiscal", is_color=False)
    db_session.add_all([user, printer])
    db_session.flush()
    db_session.add(Quota(user_id=user.id, year=2026, month=6, monthly_limit=100, used_pages=0))
    db_session.commit()

    payload = PrintJobCreate(
        username="ana",
        printer_name="Ricoh Fiscal",
        pages=2,
        is_color=False,
        external_job_id="42",
        submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )

    first = register_print_job(db_session, payload)
    second = register_print_job(db_session, payload)

    assert second.job_id == first.job_id


def test_manager_can_release_pending_job_for_same_organization(db_session):
    manager = User(username="manager-release", full_name="Manager", role=UserRole.manager, organization_id=1)
    user = User(username="release-user", full_name="Release User", role=UserRole.user, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_RELEASE", is_color=False, cost_mono=0.05, cost_color=0.25)
    db_session.add_all([manager, user, printer])
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
        document_name="Contrato.pdf",
        pages=10,
        is_color=False,
        cost=0.5,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add_all([quota, job])
    db_session.commit()

    decision = release_job(job.id, db=db_session, current_user=manager)

    assert decision.authorized is True
    assert decision.status == JobStatus.released
    db_session.refresh(quota)
    assert quota.used_pages == 10
    assert quota.used_balance == 0.5
    audit = db_session.query(AuditLog).filter(AuditLog.action == "print_job_released").one()
    assert audit.entity == "print_jobs"
    assert audit.entity_id == job.id
    assert audit.actor_user_id == manager.id
    assert audit.log_metadata["job_username"] == "release-user"
    assert audit.log_metadata["actor_role"] == "manager"
    assert audit.log_metadata["printer"] == "KONICA_RELEASE"
    assert audit.log_metadata["pages"] == 10


def test_agent_actions_match_local_queue_name_when_physical_printer_name_differs(db_session):
    agent = User(username="agent-actions", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    user = User(username="job-owner-actions", full_name="Job Owner", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA MINOLTA C368SeriesPS", is_color=True)
    db_session.add_all([agent, user, printer])
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        external_job_id="42",
        document_name="Contrato.pdf",
        queue_name="Financeiro Konica",
        pages=2,
        is_color=True,
        cost=0.50,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    actions = get_agent_actions("Financeiro Konica:42", db=db_session, current_user=agent)

    assert actions == {"Financeiro Konica:42": "hold"}


def test_manager_can_cancel_pending_job_for_same_organization(db_session):
    manager = User(username="manager-cancel", full_name="Manager", role=UserRole.manager, organization_id=1)
    user = User(username="cancel-user", full_name="Cancel User", role=UserRole.user, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_CANCEL", is_color=True, cost_mono=0.05, cost_color=0.25)
    db_session.add_all([manager, user, printer])
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        document_name="Planilha.xlsx",
        pages=3,
        is_color=True,
        cost=0.75,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    result = cancel_job(job.id, db=db_session, current_user=manager)

    assert result == {"status": "cancelled", "job_id": job.id}
    db_session.refresh(job)
    assert job.status == JobStatus.cancelled
    audit = db_session.query(AuditLog).filter(AuditLog.action == "print_job_cancelled").one()
    assert audit.entity == "print_jobs"
    assert audit.entity_id == job.id
    assert audit.actor_user_id == manager.id
    assert audit.log_metadata["job_username"] == "cancel-user"
    assert audit.log_metadata["actor_role"] == "manager"
    assert audit.log_metadata["printer"] == "KONICA_CANCEL"
    assert audit.log_metadata["pages"] == 3


def test_regular_user_cannot_release_another_users_pending_job(db_session):
    owner = User(username="job-owner", full_name="Job Owner", role=UserRole.user, organization_id=1)
    other_user = User(username="other-user", full_name="Other User", role=UserRole.user, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_PRIVATE", is_color=False)
    db_session.add_all([owner, other_user, printer])
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=owner.id,
        printer_id=printer.id,
        pages=1,
        is_color=False,
        cost=0.05,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        release_job(job.id, db=db_session, current_user=other_user)

    assert exc.value.status_code == 403
