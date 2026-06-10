from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.api.routes.jobs import cancel_job, confirm_web_printed, download_web_print_file, get_agent_actions, release_job, web_print_endpoint
from app.models.audit_log import AuditLog
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.quota import Quota
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate
from app.services.print_job_service import register_print_job


def test_print_job_payload_rejects_blank_required_names():
    with pytest.raises(ValidationError):
        PrintJobCreate(username="   ", printer_name="KONICA", pages=1, is_color=False)

    with pytest.raises(ValidationError):
        PrintJobCreate(username="diego", printer_name="   ", pages=1, is_color=False)


def test_print_job_payload_strips_names_and_ignores_blank_queue_name():
    payload = PrintJobCreate(username="  DIEGO  ", printer_name="  KONICA  ", queue_name="   ", pages=1, is_color=False)

    assert payload.username == "DIEGO"
    assert payload.printer_name == "KONICA"
    assert payload.queue_name is None


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


def test_release_blocks_and_audits_when_quota_is_insufficient_at_release(db_session):
    manager = User(username="manager-release-block", full_name="Manager", role=UserRole.manager, organization_id=1)
    user = User(username="release-block-user", full_name="Release Block User", role=UserRole.user, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_RELEASE_BLOCK", is_color=False, cost_mono=0.05, cost_color=0.25)
    db_session.add_all([manager, user, printer])
    db_session.flush()
    quota = Quota(
        organization_id=1,
        user_id=user.id,
        year=2026,
        month=6,
        monthly_limit=10,
        used_pages=8,
        monthly_balance=50.0,
        used_balance=0.0,
    )
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        document_name="Contrato.pdf",
        pages=5,
        is_color=False,
        cost=0.25,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add_all([quota, job])
    db_session.commit()

    decision = release_job(job.id, db=db_session, current_user=manager)

    db_session.refresh(job)
    db_session.refresh(quota)
    audit = db_session.query(AuditLog).filter(AuditLog.action == "print_job_blocked", AuditLog.entity_id == job.id).one()
    assert decision.authorized is False
    assert decision.status == JobStatus.blocked
    assert job.status == JobStatus.blocked
    assert quota.used_pages == 8
    assert audit.actor_user_id == manager.id
    assert audit.log_metadata["job_username"] == "release-block-user"
    assert audit.log_metadata["actor_role"] == "manager"
    assert audit.log_metadata["printer"] == "KONICA_RELEASE_BLOCK"
    assert audit.log_metadata["pages"] == 5
    assert audit.log_metadata["remaining_pages"] == 2
    assert audit.log_metadata["blocked_at_release"] is True


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


def test_agent_confirming_web_print_writes_audit(db_session):
    agent = User(username="agent-webprint", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    user = User(username="webprint-user", full_name="WebPrint User", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT", is_color=True)
    db_session.add_all([agent, user, printer])
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        external_job_id="webprint_77",
        document_name="Contrato.pdf",
        pages=7,
        is_color=True,
        cost=1.75,
        status=JobStatus.authorized,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    result = confirm_web_printed(job.id, db=db_session, current_user=agent)

    db_session.refresh(job)
    audit = db_session.query(AuditLog).filter(AuditLog.action == "web_print_confirmed", AuditLog.entity_id == job.id).one()
    assert result["success"] is True
    assert job.external_job_id == f"webprint_printed_{job.id}"
    assert audit.actor_user_id == agent.id
    assert audit.log_metadata["job_username"] == "webprint-user"
    assert audit.log_metadata["actor_role"] == "agent"
    assert audit.log_metadata["printer"] == "KONICA_WEBPRINT"
    assert audit.log_metadata["document_name"] == "Contrato.pdf"
    assert audit.log_metadata["pages"] == 7
    assert audit.log_metadata["is_color"] is True


def test_agent_cannot_confirm_pending_web_print_before_release(db_session):
    agent = User(username="agent-webprint-pending", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    user = User(username="webprint-pending-user", full_name="WebPrint Pending", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT_PENDING", is_color=True)
    db_session.add_all([agent, user, printer])
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        external_job_id="webprint_88",
        document_name="Pendente.pdf",
        pages=2,
        is_color=False,
        cost=0.10,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        confirm_web_printed(job.id, db=db_session, current_user=agent)

    db_session.refresh(job)
    assert exc.value.status_code == 400
    assert job.external_job_id == "webprint_88"
    assert db_session.query(AuditLog).filter(AuditLog.action == "web_print_confirmed").count() == 0


def test_agent_cannot_download_pending_web_print_before_release(db_session):
    agent = User(username="agent-webprint-download-pending", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    user = User(username="webprint-download-pending-user", full_name="WebPrint Pending", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT_DOWNLOAD_PENDING", is_color=True)
    db_session.add_all([agent, user, printer])
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        external_job_id="webprint_99",
        document_name="Pendente.pdf",
        pages=2,
        is_color=False,
        cost=0.10,
        status=JobStatus.pending_release,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        download_web_print_file(job.id, db=db_session, current_user=agent)

    assert exc.value.status_code == 400
    assert "download" in exc.value.detail


def test_agent_cannot_download_regular_job_through_web_print_endpoint(db_session):
    agent = User(username="agent-download-regular", full_name="Agent", role=UserRole.agent, is_active=True, organization_id=1)
    user = User(username="regular-download-user", full_name="Regular Download", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_REGULAR_DOWNLOAD", is_color=False)
    db_session.add_all([agent, user, printer])
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=printer.id,
        external_job_id="eventlog:regular-download",
        document_name="Regular.pdf",
        pages=1,
        is_color=False,
        cost=0.05,
        status=JobStatus.authorized,
        submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        download_web_print_file(job.id, db=db_session, current_user=agent)

    assert exc.value.status_code == 400
    assert "Web Print" in exc.value.detail


def test_blocked_web_print_submissions_create_distinct_jobs(db_session):
    user = User(username="webprint-blocked-user", full_name="WebPrint Blocked", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT_BLOCKED", is_color=False, cost_mono=0.05, cost_color=0.25)
    db_session.add_all([user, printer])
    db_session.flush()
    db_session.add(
        Quota(
            organization_id=1,
            user_id=user.id,
            year=2026,
            month=6,
            monthly_limit=0,
            used_pages=0,
            monthly_balance=0.0,
            used_balance=0.0,
        )
    )
    db_session.commit()

    def upload(name: str):
        return SimpleNamespace(filename=name, file=BytesIO(b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj"))

    first = web_print_endpoint(file=upload("Primeiro.pdf"), printer_id=printer.id, is_color=False, db=db_session, current_user=user)
    second = web_print_endpoint(file=upload("Segundo.pdf"), printer_id=printer.id, is_color=False, db=db_session, current_user=user)

    jobs = db_session.query(PrintJob).filter(PrintJob.printer_id == printer.id).order_by(PrintJob.id).all()
    assert first.job_id != second.job_id
    assert [job.document_name for job in jobs] == ["Primeiro.pdf", "Segundo.pdf"]
    assert [job.status for job in jobs] == [JobStatus.blocked, JobStatus.blocked]
    assert all(job.external_job_id.startswith("webprint_pending_") for job in jobs)


def test_web_print_rejects_non_pdf_uploads_without_creating_job(db_session):
    user = User(username="webprint-invalid-user", full_name="WebPrint Invalid", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT_INVALID", is_color=False)
    db_session.add_all([user, printer])
    db_session.commit()

    upload = SimpleNamespace(filename="contrato.pdf", file=BytesIO(b"nao e pdf"))

    with pytest.raises(HTTPException) as exc:
        web_print_endpoint(file=upload, printer_id=printer.id, is_color=False, db=db_session, current_user=user)

    assert exc.value.status_code == 400
    assert "PDF" in exc.value.detail
    assert db_session.query(PrintJob).filter(PrintJob.printer_id == printer.id).count() == 0


def test_web_print_rejects_uploads_above_configured_limit(db_session, monkeypatch):
    user = User(username="webprint-large-user", full_name="WebPrint Large", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT_LARGE", is_color=False)
    db_session.add_all([user, printer])
    db_session.commit()
    monkeypatch.setattr("app.api.routes.jobs.settings.web_print_max_upload_mb", 1)
    content = b"%PDF-1.4\n" + (b"0" * (3 * 1024 * 1024))
    upload = SimpleNamespace(filename="grande.pdf", file=BytesIO(content))

    with pytest.raises(HTTPException) as exc:
        web_print_endpoint(file=upload, printer_id=printer.id, is_color=False, db=db_session, current_user=user)

    assert exc.value.status_code == 413
    assert upload.file.tell() < len(content)
    assert db_session.query(PrintJob).filter(PrintJob.printer_id == printer.id).count() == 0


def test_web_print_sanitizes_uploaded_filename(db_session):
    user = User(username="webprint-clean-user", full_name="WebPrint Clean", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT_CLEAN", is_color=False)
    db_session.add_all([user, printer])
    db_session.commit()

    upload = SimpleNamespace(filename="C:\\temp\\Contrato Final.pdf", file=BytesIO(b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj"))

    decision = web_print_endpoint(file=upload, printer_id=printer.id, is_color=False, db=db_session, current_user=user)

    job = db_session.get(PrintJob, decision.job_id)
    assert job.document_name == "Contrato Final.pdf"


def test_web_print_saves_pdf_in_configured_upload_dir(db_session, tmp_path, monkeypatch):
    upload_dir = tmp_path / "custom-web-print"
    monkeypatch.setattr("app.api.routes.jobs.settings.web_print_upload_dir", str(upload_dir))
    user = User(username="webprint-dir-user", full_name="WebPrint Dir", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_WEBPRINT_DIR", is_color=False)
    db_session.add_all([user, printer])
    db_session.commit()

    upload = SimpleNamespace(filename="Arquivo.pdf", file=BytesIO(b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj"))

    decision = web_print_endpoint(file=upload, printer_id=printer.id, is_color=False, db=db_session, current_user=user)

    assert (upload_dir / f"webprint_{decision.job_id}.pdf").exists()
    assert not (Path("uploads") / f"webprint_{decision.job_id}.pdf").exists()


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
