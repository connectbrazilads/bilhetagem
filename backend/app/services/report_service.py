from datetime import datetime, time, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.user import User


def dashboard_metrics(db: Session, organization_id: int | None = None) -> dict:
    if organization_id is None:
        from app.services.organization_service import get_or_create_default_organization
        organization_id = get_or_create_default_organization(db).id
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    authorized = PrintJob.status.in_([JobStatus.authorized, JobStatus.released])
    org_filter = PrintJob.organization_id == organization_id
    prints_today = db.query(func.count(PrintJob.id)).filter(org_filter, authorized, PrintJob.submitted_at >= today_start).scalar() or 0
    prints_month = db.query(func.count(PrintJob.id)).filter(org_filter, authorized, PrintJob.submitted_at >= month_start).scalar() or 0
    pages_today = db.query(func.coalesce(func.sum(PrintJob.pages), 0)).filter(
        org_filter, authorized, PrintJob.submitted_at >= today_start
    ).scalar() or 0
    pages_month = db.query(func.coalesce(func.sum(PrintJob.pages), 0)).filter(
        org_filter, authorized, PrintJob.submitted_at >= month_start
    ).scalar() or 0

    top_users = [
        {"username": full_name or username, "pages": pages}
        for username, full_name, pages in db.query(User.username, User.full_name, func.sum(PrintJob.pages))
        .join(PrintJob, PrintJob.user_id == User.id)
        .filter(org_filter, authorized, PrintJob.submitted_at >= month_start)
        .group_by(User.username, User.full_name)
        .order_by(func.sum(PrintJob.pages).desc())
        .limit(5)
        .all()
    ]
    top_printers = [
        {"printer": printer, "pages": pages}
        for printer, pages in db.query(Printer.name, func.sum(PrintJob.pages))
        .join(PrintJob, PrintJob.printer_id == Printer.id)
        .filter(org_filter, authorized, PrintJob.submitted_at >= month_start)
        .group_by(Printer.name)
        .order_by(func.sum(PrintJob.pages).desc())
        .limit(5)
        .all()
    ]
    department_usage = [
        {"department": department or "Sem departamento", "pages": pages}
        for department, pages in db.query(Department.name, func.sum(PrintJob.pages))
        .select_from(PrintJob)
        .join(User, User.id == PrintJob.user_id)
        .outerjoin(Department, Department.id == User.department_id)
        .filter(org_filter, authorized, PrintJob.submitted_at >= month_start)
        .group_by(Department.name)
        .order_by(func.sum(PrintJob.pages).desc())
        .all()
    ]
    color_usage = [
        {"type": "Colorido" if is_color else "Preto e branco", "pages": pages}
        for is_color, pages in db.query(PrintJob.is_color, func.coalesce(func.sum(PrintJob.pages), 0))
        .filter(org_filter, authorized, PrintJob.submitted_at >= month_start)
        .group_by(PrintJob.is_color)
        .all()
    ]

    # Calculate Eco savings: blocked or cancelled jobs
    saved = PrintJob.status.in_([JobStatus.blocked, JobStatus.cancelled])
    pages_saved_month = db.query(func.coalesce(func.sum(PrintJob.pages), 0)).filter(
        org_filter, saved, PrintJob.submitted_at >= month_start
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
