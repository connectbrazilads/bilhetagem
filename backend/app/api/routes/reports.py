from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.monthly_closing import MonthlyClosing
from app.models.print_job import PrintJob
from app.models.user import User, UserRole
from app.schemas.report import (
    DashboardMetrics,
    MonthlyClosingCreate,
    MonthlyClosingDueEmailRead,
    MonthlyClosingEmailRead,
    MonthlyClosingEmailRequest,
    MonthlyClosingRead,
)
from app.services.email_service import send_due_monthly_report_email, send_monthly_closing_email
from app.services.monthly_closing_service import create_monthly_closing
from app.services.report_export_service import monthly_closing_filename_base, render_monthly_closing_pdf, render_monthly_closing_xlsx
from app.services.report_service import dashboard_metrics

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=DashboardMetrics)
def get_reports(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> dict:
    return dashboard_metrics(db, actor.organization_id)


@router.get("/monthly-closings", response_model=list[MonthlyClosingRead])
def list_monthly_closings(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[MonthlyClosing]:
    return (
        db.query(MonthlyClosing)
        .filter(MonthlyClosing.organization_id == actor.organization_id)
        .order_by(MonthlyClosing.year.desc(), MonthlyClosing.month.desc())
        .all()
    )


@router.post("/monthly-closings", response_model=MonthlyClosingRead)
def generate_monthly_closing(
    payload: MonthlyClosingCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> MonthlyClosing:
    return create_monthly_closing(db, actor.organization_id, payload.year, payload.month)


@router.post("/monthly-closings/email-due", response_model=MonthlyClosingDueEmailRead)
def send_due_monthly_closing_email_endpoint(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    try:
        return send_due_monthly_report_email(db, actor.organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/monthly-closings/{closing_id}", response_model=MonthlyClosingRead)
def get_monthly_closing(
    closing_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> MonthlyClosing:
    closing = db.query(MonthlyClosing).filter(MonthlyClosing.organization_id == actor.organization_id, MonthlyClosing.id == closing_id).first()
    if not closing:
        raise HTTPException(status_code=404, detail="Fechamento nao encontrado")
    return closing


@router.post("/monthly-closings/{closing_id}/email", response_model=MonthlyClosingEmailRead)
def send_monthly_closing_email_endpoint(
    closing_id: int,
    payload: MonthlyClosingEmailRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    closing = _closing_or_404(db, actor.organization_id, closing_id)
    payload = payload or MonthlyClosingEmailRequest()
    try:
        return send_monthly_closing_email(
            db,
            closing,
            recipients=payload.recipients,
            include_pdf=payload.include_pdf,
            include_xlsx=payload.include_xlsx,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _closing_or_404(db: Session, organization_id: int, closing_id: int) -> MonthlyClosing:
    closing = db.query(MonthlyClosing).filter(MonthlyClosing.organization_id == organization_id, MonthlyClosing.id == closing_id).first()
    if not closing:
        raise HTTPException(status_code=404, detail="Fechamento nao encontrado")
    return closing


@router.get("/monthly-closings/{closing_id}/export")
def export_monthly_closing(
    closing_id: int,
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Response:
    closing = _closing_or_404(db, actor.organization_id, closing_id)
    filename_base = monthly_closing_filename_base(closing)

    if format == "pdf":
        return Response(
            content=render_monthly_closing_pdf(closing),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"},
        )

    return Response(
        content=render_monthly_closing_xlsx(closing),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"},
    )


@router.get("/export")
def export_report(
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
    user_id: int | None = None,
    department_id: int | None = None,
    printer_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Response:
    query = db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id).order_by(PrintJob.submitted_at.desc())
    if user_id:
        query = query.filter(PrintJob.user_id == user_id)
    if department_id:
        query = query.filter(PrintJob.user.has(User.department_id == department_id))
    if printer_id:
        query = query.filter(PrintJob.printer_id == printer_id)
    if date_from:
        query = query.filter(PrintJob.submitted_at >= date_from)
    if date_to:
        query = query.filter(PrintJob.submitted_at <= date_to)
    jobs = query.limit(5000).all()

    if format == "pdf":
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        pdf.setTitle("Relatório de Impressões")
        pdf.drawString(40, 800, "Relatório de Impressões")
        y = 770
        for job in jobs[:45]:
            doc = (job.document_name[:30] + "...") if (job.document_name and len(job.document_name) > 30) else (job.document_name or "N/A")
            user_name = job.user.full_name or job.user.username
            department_name = job.user.department.name if job.user.department else "Sem departamento"
            pdf.drawString(40, y, f"{job.submitted_at:%Y-%m-%d %H:%M} | {user_name} | {department_name} | {job.printer.name} | {doc} | {job.pages} pag. | R$ {job.cost:.2f}")
            y -= 16
        pdf.save()
        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=relatorio-impressoes.pdf"},
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Impressões"
    sheet.append(["Data", "Usuário", "Departamento", "Impressora", "Documento", "Páginas", "Cor", "Status", "Custo"])
    for job in jobs:
        sheet.append([
            job.submitted_at.isoformat(),
            job.user.full_name or job.user.username,
            job.user.department.name if job.user.department else "Sem departamento",
            job.printer.name,
            job.document_name or "",
            job.pages,
            job.is_color,
            job.status.value,
            job.cost,
        ])
    buffer = BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=relatorio-impressoes.xlsx"},
    )
