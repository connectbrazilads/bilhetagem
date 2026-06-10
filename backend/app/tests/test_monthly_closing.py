from datetime import datetime, timezone
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.api.routes.reports import export_monthly_closing, export_report, generate_monthly_closing
from app.api.routes.settings import get_monthly_report_email_settings_endpoint, update_monthly_report_email_settings_endpoint
from app.models.department import Department
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.schemas.settings import MonthlyReportEmailSettings
from app.schemas.report import MonthlyClosingCreate
from app.services.email_service import send_due_monthly_report_email, send_monthly_closing_email
from app.services.email_scheduler import send_due_monthly_reports_once
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
    workbook = load_workbook(BytesIO(response.body), data_only=True)
    assert workbook.sheetnames == ["Resumo", "Usuarios", "Departamentos", "Impressoras", "Tipo"]
    assert workbook["Resumo"]["A12"].value == "Custo total"
    assert workbook["Resumo"]["B12"].value == 1.5
    assert workbook["Impressoras"]["A2"].value == "KONICA_FECHAMENTO"
    audit = db_session.query(AuditLog).filter(AuditLog.action == "monthly_closing_exported", AuditLog.entity_id == closing.id).one()
    assert audit.log_metadata == {"format": "xlsx"}


def test_monthly_closing_export_pdf(db_session: Session):
    _seed_job_data(db_session)
    closing = create_monthly_closing(db_session, organization_id=1, year=2026, month=5)
    actor = User(username="report-pdf-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    response = export_monthly_closing(closing_id=closing.id, format="pdf", db=db_session, actor=actor)

    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")


def test_report_export_applies_department_filter(db_session: Session):
    user, printer = _seed_job_data(db_session)
    other_department = Department(organization_id=1, name="Juridico")
    other_user = User(username="bia", full_name="Bia Juridico", role=UserRole.user, department=other_department, is_active=True, organization_id=1)
    other_printer = Printer(organization_id=1, name="HP_JURIDICO", is_color=False, cost_mono=0.05, cost_color=0.25)
    db_session.add_all([other_department, other_user, other_printer])
    db_session.flush()
    db_session.add(
        PrintJob(
            organization_id=1,
            user_id=other_user.id,
            printer_id=other_printer.id,
            pages=2,
            is_color=False,
            cost=0.10,
            status=JobStatus.authorized,
            submitted_at=datetime(2026, 5, 13, 10, tzinfo=timezone.utc),
        )
    )
    actor = User(username="report-filter-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    response = export_report(format="xlsx", department_id=user.department_id, db=db_session, actor=actor)

    workbook = load_workbook(BytesIO(response.body), data_only=True)
    sheet = workbook.active
    exported_users = [row[1].value for row in sheet.iter_rows(min_row=2)]
    assert set(exported_users) == {"Ana Financeiro"}
    assert len(exported_users) == 4
    assert sheet["C2"].value == "Financeiro"
    assert sheet["I2"].value in {0.5, 1.0, 0.75, 4.95}


def test_monthly_report_email_settings_api(db_session: Session):
    actor = User(username="email-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    initial = get_monthly_report_email_settings_endpoint(db=db_session, actor=actor)
    assert initial.enabled is False
    assert initial.day_of_month == 1

    updated = update_monthly_report_email_settings_endpoint(
        payload=MonthlyReportEmailSettings(
            enabled=True,
            recipients="financeiro@example.com; gestao@example.com",
            day_of_month=5,
            include_pdf=True,
            include_xlsx=False,
        ),
        db=db_session,
        actor=actor,
    )

    assert updated.enabled is True
    assert updated.recipients == "financeiro@example.com; gestao@example.com"
    assert updated.day_of_month == 5
    assert updated.include_xlsx is False


def test_generate_monthly_closing_endpoint_writes_audit(db_session: Session):
    _seed_job_data(db_session)
    actor = User(username="closing-audit-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(actor)
    db_session.commit()

    closing = generate_monthly_closing(MonthlyClosingCreate(year=2026, month=5), db=db_session, actor=actor)

    audit = db_session.query(AuditLog).filter(AuditLog.action == "monthly_closing_generated", AuditLog.entity_id == closing.id).one()
    assert audit.actor_user_id == actor.id
    assert audit.log_metadata["year"] == 2026
    assert audit.log_metadata["month"] == 5
    assert audit.log_metadata["total_pages"] == 14
    assert audit.log_metadata["total_cost"] == 1.5


def test_send_monthly_closing_email_with_attachments(db_session: Session, monkeypatch):
    _seed_job_data(db_session)
    closing = create_monthly_closing(db_session, organization_id=1, year=2026, month=5)
    sent_messages = []

    class DummySMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            return None

        def login(self, username, password):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("app.services.email_service.settings.smtp_host", "smtp.example.com")
    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", DummySMTP)

    result = send_monthly_closing_email(
        db_session,
        closing,
        recipients="financeiro@example.com,gestao@example.com",
    )

    assert result["sent"] is True
    assert result["recipients"] == ["financeiro@example.com", "gestao@example.com"]
    assert result["attachments"] == ["fechamento-2026-05.pdf", "fechamento-2026-05.xlsx"]
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "financeiro@example.com, gestao@example.com"
    assert [part.get_filename() for part in sent_messages[0].iter_attachments()] == result["attachments"]


def test_due_monthly_report_email_sends_previous_month_once(db_session: Session, monkeypatch):
    _seed_job_data(db_session)
    sent_messages = []

    class DummySMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("app.services.email_service.settings.smtp_host", "smtp.example.com")
    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", DummySMTP)
    update_monthly_report_email_settings_endpoint(
        payload=MonthlyReportEmailSettings(
            enabled=True,
            recipients="financeiro@example.com",
            day_of_month=1,
            include_pdf=True,
            include_xlsx=False,
        ),
        db=db_session,
        actor=User(username="email-due-admin", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1),
    )

    first = send_due_monthly_report_email(db_session, organization_id=1, now=datetime(2026, 6, 10, tzinfo=timezone.utc))
    second = send_due_monthly_report_email(db_session, organization_id=1, now=datetime(2026, 6, 10, tzinfo=timezone.utc))

    assert first["sent"] is True
    assert first["period"] == "2026-05"
    assert first["attachments"] == ["fechamento-2026-05.pdf"]
    assert second["sent"] is False
    assert second["reason"] == "Fechamento mensal ja enviado"
    assert len(sent_messages) == 1


def test_monthly_report_email_scheduler_processes_active_organizations(db_session: Session, monkeypatch):
    active_org = Organization(name="Cliente Scheduler", slug="cliente-scheduler", is_active=True)
    inactive_org = Organization(name="Cliente Scheduler Inativo", slug="cliente-scheduler-inativo", is_active=False)
    db_session.add_all([active_org, inactive_org])
    db_session.commit()

    called_organization_ids = []

    def fake_send_due(db, organization_id, now=None):
        called_organization_ids.append(organization_id)
        if organization_id == 1:
            return {
                "sent": True,
                "period": "2026-05",
                "closing_id": 99,
                "recipients": ["financeiro@example.com"],
                "attachments": ["fechamento-2026-05.pdf"],
                "reason": None,
            }
        return {"sent": False, "reason": "Envio mensal desativado"}

    monkeypatch.setattr("app.services.email_scheduler.send_due_monthly_report_email", fake_send_due)

    results = send_due_monthly_reports_once(db_session, now=datetime(2026, 6, 10, tzinfo=timezone.utc))

    assert called_organization_ids == [1, active_org.id]
    assert [result["organization_slug"] for result in results] == ["default", "cliente-scheduler"]
    audit = db_session.query(AuditLog).filter(AuditLog.action == "monthly_closing_due_email_sent").one()
    assert audit.organization_id == 1
    assert audit.entity_id == 99
    assert audit.log_metadata["automatic"] is True
