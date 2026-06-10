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
from app.schemas.report import DashboardMetrics, MonthlyClosingCreate, MonthlyClosingRead
from app.services.monthly_closing_service import create_monthly_closing
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
    filename_base = f"fechamento-{closing.year}-{closing.month:02d}"
    snapshot = closing.snapshot

    if format == "pdf":
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        pdf.setTitle("Fechamento Mensal")
        pdf.drawString(40, 800, f"Fechamento Mensal - {closing.month:02d}/{closing.year}")
        pdf.drawString(40, 780, f"Paginas: {closing.total_pages} | Custo: R$ {closing.total_cost:.2f} | Bloqueadas/salvas: {closing.blocked_pages}")
        y = 750
        pdf.drawString(40, y, "Por impressora")
        y -= 18
        for row in snapshot.get("by_printer", [])[:20]:
            pdf.drawString(40, y, f"{row['name']} | {row['pages']} pag. | P&B {row['mono_pages']} | Cor {row['color_pages']} | R$ {row['cost']:.2f}")
            y -= 16
            if y < 80:
                pdf.showPage()
                y = 800
        pdf.save()
        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"},
        )

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Resumo"
    summary.append(["Periodo", f"{closing.month:02d}/{closing.year}"])
    summary.append(["Trabalhos", closing.total_jobs])
    summary.append(["Trabalhos cobraveis", closing.billable_jobs])
    summary.append(["Paginas", closing.total_pages])
    summary.append(["P&B", closing.mono_pages])
    summary.append(["Coloridas", closing.color_pages])
    summary.append(["Bloqueadas/Salvas", closing.blocked_pages])
    summary.append(["Custo", closing.total_cost])

    for sheet_name, key in (("Usuarios", "by_user"), ("Departamentos", "by_department"), ("Impressoras", "by_printer"), ("Tipo", "by_type")):
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(["Nome", "Trabalhos", "Paginas", "P&B", "Coloridas", "Custo"])
        for row in snapshot.get(key, []):
            sheet.append([row["name"], row["jobs"], row["pages"], row["mono_pages"], row["color_pages"], row["cost"]])

    buffer = BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"},
    )


@router.get("/export")
def export_report(
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Response:
    query = db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id).order_by(PrintJob.submitted_at.desc())
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
