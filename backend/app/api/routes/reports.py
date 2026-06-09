from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, Query, Response
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.print_job import PrintJob
from app.models.user import User, UserRole
from app.schemas.report import DashboardMetrics
from app.services.report_service import dashboard_metrics

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=DashboardMetrics)
def get_reports(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> dict:
    return dashboard_metrics(db)


@router.get("/export")
def export_report(
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Response:
    query = db.query(PrintJob).order_by(PrintJob.submitted_at.desc())
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
            pdf.drawString(40, y, f"{job.submitted_at:%Y-%m-%d %H:%M} | {user_name} | {job.printer.name} | {doc} | {job.pages} pág.")
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
    sheet.append(["Data", "Usuário", "Impressora", "Documento", "Páginas", "Cor", "Status"])
    for job in jobs:
        sheet.append([job.submitted_at.isoformat(), job.user.full_name or job.user.username, job.printer.name, job.document_name or "", job.pages, job.is_color, job.status.value])
    buffer = BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=relatorio-impressoes.xlsx"},
    )
