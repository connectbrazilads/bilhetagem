from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.department import Department
from app.models.monthly_closing import MonthlyClosing
from app.models.print_job import PrintJob
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.schemas.report import (
    DashboardMetrics,
    MonthlyClosingCreate,
    MonthlyClosingDueEmailRead,
    MonthlyClosingEmailRead,
    MonthlyClosingEmailRequest,
    MonthlyClosingRead,
)
from app.services.audit_service import write_audit
from app.services.email_service import send_due_monthly_report_email, send_monthly_closing_email
from app.services.monthly_closing_service import create_monthly_closing
from app.services.report_export_service import (
    monthly_closing_filename_base,
    render_monthly_closing_pdf,
    render_monthly_closing_xlsx,
    render_print_jobs_pdf,
    render_print_jobs_xlsx,
)
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
    closing = create_monthly_closing(db, actor.organization_id, payload.year, payload.month)
    write_audit(
        db,
        action="monthly_closing_generated",
        entity="monthly_closings",
        entity_id=closing.id,
        actor_user_id=actor.id,
        metadata={"year": closing.year, "month": closing.month, "total_pages": closing.total_pages, "total_cost": closing.total_cost},
    )
    db.commit()
    return closing


@router.post("/monthly-closings/email-due", response_model=MonthlyClosingDueEmailRead)
def send_due_monthly_closing_email_endpoint(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    try:
        result = send_due_monthly_report_email(db, actor.organization_id)
        if result.get("sent"):
            write_audit(
                db,
                action="monthly_closing_due_email_sent",
                entity="monthly_closings",
                entity_id=result.get("closing_id"),
                actor_user_id=actor.id,
                metadata={"period": result.get("period"), "recipients": result.get("recipients", []), "attachments": result.get("attachments", [])},
            )
            db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        result = send_monthly_closing_email(
            db,
            closing,
            recipients=payload.recipients,
            include_pdf=payload.include_pdf,
            include_xlsx=payload.include_xlsx,
        )
        write_audit(
            db,
            action="monthly_closing_email_sent",
            entity="monthly_closings",
            entity_id=closing.id,
            actor_user_id=actor.id,
            metadata={"recipients": result["recipients"], "attachments": result["attachments"]},
        )
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _closing_or_404(db: Session, organization_id: int, closing_id: int) -> MonthlyClosing:
    closing = db.query(MonthlyClosing).filter(MonthlyClosing.organization_id == organization_id, MonthlyClosing.id == closing_id).first()
    if not closing:
        raise HTTPException(status_code=404, detail="Fechamento nao encontrado")
    return closing


def _report_filter_summary(
    db: Session,
    organization_id: int,
    *,
    user_id: int | None,
    department_id: int | None,
    printer_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    if user_id:
        user = db.query(User).filter(User.organization_id == organization_id, User.id == user_id).first()
        filters["Usuario"] = (user.full_name or user.username) if user else f"ID {user_id}"
    if department_id:
        department = db.query(Department).filter(Department.organization_id == organization_id, Department.id == department_id).first()
        filters["Departamento"] = department.name if department else f"ID {department_id}"
    if printer_id:
        printer = db.query(Printer).filter(Printer.organization_id == organization_id, Printer.id == printer_id).first()
        filters["Impressora"] = printer.name if printer else f"ID {printer_id}"
    if date_from or date_to:
        start = date_from.strftime("%d/%m/%Y %H:%M") if date_from else "inicio"
        end = date_to.strftime("%d/%m/%Y %H:%M") if date_to else "agora"
        filters["Periodo"] = f"{start} ate {end}"
    return filters


@router.get("/monthly-closings/{closing_id}/export")
def export_monthly_closing(
    closing_id: int,
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Response:
    closing = _closing_or_404(db, actor.organization_id, closing_id)
    filename_base = monthly_closing_filename_base(closing)
    write_audit(
        db,
        action="monthly_closing_exported",
        entity="monthly_closings",
        entity_id=closing.id,
        actor_user_id=actor.id,
        metadata={"format": format},
    )
    db.commit()

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
    query = (
        db.query(PrintJob)
        .join(User, User.id == PrintJob.user_id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .filter(
            PrintJob.organization_id == actor.organization_id,
            User.organization_id == actor.organization_id,
            Printer.organization_id == actor.organization_id,
        )
        .order_by(PrintJob.submitted_at.desc())
    )
    if user_id:
        query = query.filter(PrintJob.user_id == user_id)
    if department_id:
        query = query.outerjoin(Department, Department.id == User.department_id).filter(
            User.department_id == department_id,
            Department.organization_id == actor.organization_id,
        )
    if printer_id:
        query = query.filter(PrintJob.printer_id == printer_id)
    if date_from:
        query = query.filter(PrintJob.submitted_at >= date_from)
    if date_to:
        query = query.filter(PrintJob.submitted_at <= date_to)
    jobs = query.limit(5000).all()
    filter_summary = _report_filter_summary(
        db,
        actor.organization_id,
        user_id=user_id,
        department_id=department_id,
        printer_id=printer_id,
        date_from=date_from,
        date_to=date_to,
    )
    write_audit(
        db,
        action="report_exported",
        entity="print_jobs",
        actor_user_id=actor.id,
        metadata={
            "format": format,
            "rows": len(jobs),
            "filters": {
                "user_id": user_id,
                "department_id": department_id,
                "printer_id": printer_id,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
        },
    )
    db.commit()

    if format == "pdf":
        return Response(
            content=render_print_jobs_pdf(jobs, filters=filter_summary),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=relatorio-impressoes.pdf"},
        )

    return Response(
        content=render_print_jobs_xlsx(jobs, filters=filter_summary),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=relatorio-impressoes.xlsx"},
    )
