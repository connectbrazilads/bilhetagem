from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.routes.reports import export_monthly_closing
from app.models.department import Department
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.services.monthly_closing_service import create_monthly_closing


def _seed_job_data(db_session: Session) -> tuple[User, Printer]:
    department = Department(organization_id=1, name="Financeiro")
    user = User(username="ana", full_name="Ana Financeiro", role=UserRole.user, department=department, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA_FECHAMENTO", is_color=True, cost_mono=0.05, cost_color=0.25)
    db_session.add_all([department, user, printer])
    db_session.flush()
    jobs = [
        PrintJob(
            organization_id=1,
            user_id=user.id,
            printer_id=printer.id,
            pages=10,
            is_color=False,
            cost=0.50,
            status=JobStatus.authorized,
            submitted_at=datetime(2026, 5, 10, 10, tzinfo=timezone.utc),
        ),
        PrintJob(
            organization_id=1,
            user_id=user.id,
            printer_id=printer.id,
            pages=4,
            is_color=True,
            cost=1.00,
            status=JobStatus.released,
            submitted_at=datetime(2026, 5, 11, 10, tzinfo=timezone.utc),
        ),
        PrintJob(
            organization_id=1,
            user_id=user.id,
            printer_id=printer.id,
            pages=3,
            is_color=True,
            cost=0.75,
            status=JobStatus.blocked,
            submitted_at=datetime(2026, 5, 12, 10, tzinfo=timezone.utc),
        ),
        PrintJob(
            organization_id=1,
            user_id=user.id,
            printer_id=printer.id,
            pages=99,
            is_color=False,
            cost=4.95,
            status=JobStatus.authorized,
            submitted_at=datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
        ),
    ]
    db_session.add_all(jobs)
    db_session.commit()
    return user, printer


def test_monthly_closing_freezes_commercial_snapshot(db_session: Session):
    user, printer = _seed_job_data(db_session)

    closing = create_monthly_closing(db_session, organization_id=1, year=2026, month=5)

    assert closing.total_jobs == 3
    assert closing.billable_jobs == 2
    assert closing.total_pages == 14
    assert closing.mono_pages == 10
    assert closing.color_pages == 4
    assert closing.blocked_pages == 3
    assert closing.total_cost == 1.5
    assert closing.snapshot["by_user"][0]["name"] == "Ana Financeiro"
    assert closing.snapshot["by_printer"][0]["name"] == "KONICA_FECHAMENTO"

    user.full_name = "Ana Renomeada"
    printer.name = "KONICA_NOVA"
    db_session.commit()
    same_closing = create_monthly_closing(db_session, organization_id=1, year=2026, month=5)

    assert same_closing.id == closing.id
    assert same_closing.snapshot["by_user"][0]["name"] == "Ana Financeiro"
    assert same_closing.snapshot["by_printer"][0]["name"] == "KONICA_FECHAMENTO"


def test_monthly_closing_export_xlsx(db_session: Session):
    _seed_job_data(db_session)
    closing = create_monthly_closing(db_session, organization_id=1, year=2026, month=5)
    actor = User(username="report-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    response = export_monthly_closing(closing_id=closing.id, format="xlsx", db=db_session, actor=actor)

    assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.body.startswith(b"PK")
