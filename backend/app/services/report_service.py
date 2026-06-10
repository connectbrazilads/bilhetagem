from datetime import datetime, time, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.user import User


def _round_money(value: float) -> float:
    return round(float(value or 0.0), 2)


def _cost_per_page(cost: float, pages: int) -> float:
    if pages <= 0:
        return 0.0
    return _round_money(cost / pages)


def _scoped_job_query(db: Session, organization_id: int):
    return (
        db.query(PrintJob)
        .join(User, User.id == PrintJob.user_id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .filter(
            PrintJob.organization_id == organization_id,
            User.organization_id == organization_id,
            Printer.organization_id == organization_id,
        )
    )


def dashboard_metrics(db: Session, organization_id: int | None = None) -> dict:
    if organization_id is None:
        from app.services.organization_service import get_or_create_default_organization
        organization_id = get_or_create_default_organization(db).id
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    authorized = PrintJob.status.in_([JobStatus.authorized, JobStatus.released])
    scoped_jobs = _scoped_job_query(db, organization_id)
    prints_today = scoped_jobs.with_entities(func.count(PrintJob.id)).filter(authorized, PrintJob.submitted_at >= today_start).scalar() or 0
    prints_month = scoped_jobs.with_entities(func.count(PrintJob.id)).filter(authorized, PrintJob.submitted_at >= month_start).scalar() or 0
    pages_today = scoped_jobs.with_entities(func.coalesce(func.sum(PrintJob.pages), 0)).filter(
        authorized, PrintJob.submitted_at >= today_start
    ).scalar() or 0
    pages_month = scoped_jobs.with_entities(func.coalesce(func.sum(PrintJob.pages), 0)).filter(
        authorized, PrintJob.submitted_at >= month_start
    ).scalar() or 0

    top_users = [
        {
            "username": full_name or username,
            "pages": int(pages or 0),
            "cost": _round_money(cost),
            "cost_per_page": _cost_per_page(cost, int(pages or 0)),
        }
        for username, full_name, pages, cost in db.query(
            User.username,
            User.full_name,
            func.sum(PrintJob.pages),
            func.coalesce(func.sum(PrintJob.cost), 0.0),
        )
        .join(PrintJob, PrintJob.user_id == User.id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .filter(
            PrintJob.organization_id == organization_id,
            User.organization_id == organization_id,
            Printer.organization_id == organization_id,
            authorized,
            PrintJob.submitted_at >= month_start,
        )
        .group_by(User.username, User.full_name)
        .order_by(func.sum(PrintJob.pages).desc())
        .limit(5)
        .all()
    ]
    top_printers = [
        {
            "printer": printer,
            "pages": int(pages or 0),
            "cost": _round_money(cost),
            "cost_per_page": _cost_per_page(cost, int(pages or 0)),
        }
        for printer, pages, cost in db.query(
            Printer.name,
            func.sum(PrintJob.pages),
            func.coalesce(func.sum(PrintJob.cost), 0.0),
        )
        .join(PrintJob, PrintJob.printer_id == Printer.id)
        .join(User, User.id == PrintJob.user_id)
        .filter(
            PrintJob.organization_id == organization_id,
            User.organization_id == organization_id,
            Printer.organization_id == organization_id,
            authorized,
            PrintJob.submitted_at >= month_start,
        )
        .group_by(Printer.name)
        .order_by(func.sum(PrintJob.pages).desc())
        .limit(5)
        .all()
    ]
    department_usage = [
        {
            "department": department or "Sem departamento",
            "pages": int(pages or 0),
            "cost": _round_money(cost),
            "cost_per_page": _cost_per_page(cost, int(pages or 0)),
        }
        for department, pages, cost in db.query(
            Department.name,
            func.sum(PrintJob.pages),
            func.coalesce(func.sum(PrintJob.cost), 0.0),
        )
        .select_from(PrintJob)
        .join(User, User.id == PrintJob.user_id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .outerjoin(Department, Department.id == User.department_id)
        .filter(
            PrintJob.organization_id == organization_id,
            User.organization_id == organization_id,
            Printer.organization_id == organization_id,
            or_(Department.id.is_(None), Department.organization_id == organization_id),
            authorized,
            PrintJob.submitted_at >= month_start,
        )
        .group_by(Department.name)
        .order_by(func.sum(PrintJob.pages).desc())
        .all()
    ]
    color_usage = [
        {
            "type": "Colorido" if is_color else "Preto e branco",
            "pages": int(pages or 0),
            "cost": _round_money(cost),
            "cost_per_page": _cost_per_page(cost, int(pages or 0)),
        }
        for is_color, pages, cost in db.query(
            PrintJob.is_color,
            func.coalesce(func.sum(PrintJob.pages), 0),
            func.coalesce(func.sum(PrintJob.cost), 0.0),
        )
        .join(User, User.id == PrintJob.user_id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .filter(
            PrintJob.organization_id == organization_id,
            User.organization_id == organization_id,
            Printer.organization_id == organization_id,
            authorized,
            PrintJob.submitted_at >= month_start,
        )
        .group_by(PrintJob.is_color)
        .all()
    ]

    # Calculate Eco savings: blocked or cancelled jobs
    saved = PrintJob.status.in_([JobStatus.blocked, JobStatus.cancelled])
    pages_saved_month = scoped_jobs.with_entities(func.coalesce(func.sum(PrintJob.pages), 0)).filter(
        saved, PrintJob.submitted_at >= month_start
    ).scalar() or 0

    co2_saved = float(pages_saved_month) * 4.7
    water_saved = float(pages_saved_month) * 1.0
    trees_saved = float(pages_saved_month) * 0.0001

    return {
        "prints_today": prints_today,
        "prints_month": prints_month,
        "pages_today": pages_today,
        "pages_month": pages_month,
        "top_users": top_users,
        "top_printers": top_printers,
        "department_usage": department_usage,
        "color_usage": color_usage,
        "eco_metrics": {
            "pages_saved": pages_saved_month,
            "co2_saved_g": co2_saved,
            "water_saved_l": water_saved,
            "trees_saved": trees_saved
        }
    }
