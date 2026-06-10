from datetime import datetime, time, timedelta, timezone
from collections import defaultdict

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.print_agent import PrintAgent
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User

AGENT_ONLINE_WINDOW = timedelta(minutes=3)


def _round_money(value: float) -> float:
    return round(float(value or 0.0), 2)


def _cost_per_page(cost: float, pages: int) -> float:
    if pages <= 0:
        return 0.0
    return _round_money(cost / pages)


def _normalize_alias_name(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _duplicate_queue_alias_count(aliases: list[PrinterAlias]) -> int:
    grouped: dict[tuple[int | None, str], int] = {}
    for alias in aliases:
        normalized = alias.normalized_queue_name or _normalize_alias_name(alias.queue_name)
        if not normalized:
            continue
        key = (alias.agent_id, normalized)
        grouped[key] = grouped.get(key, 0) + 1
    return sum(count - 1 for count in grouped.values() if count > 1)


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


def _agent_is_online(agent: PrintAgent, now: datetime) -> bool:
    if not agent.last_seen_at:
        return False
    last_seen = agent.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return now - last_seen <= AGENT_ONLINE_WINDOW


def _alias_is_present(agent: PrintAgent, alias: PrinterAlias) -> bool:
    if not agent.last_seen_at or not alias.last_seen_at:
        return False
    agent_seen = agent.last_seen_at
    alias_seen = alias.last_seen_at
    if agent_seen.tzinfo is None:
        agent_seen = agent_seen.replace(tzinfo=timezone.utc)
    if alias_seen.tzinfo is None:
        alias_seen = alias_seen.replace(tzinfo=timezone.utc)
    return alias_seen >= agent_seen


def _agent_has_operational_alert(agent: PrintAgent, aliases: list[PrinterAlias], now: datetime) -> bool:
    if not _agent_is_online(agent, now):
        return True
    if agent.last_error or agent.event_log_enabled is False:
        return True

    present_aliases = [alias for alias in aliases if _alias_is_present(agent, alias)]
    if agent.last_seen_at and not present_aliases:
        return True
    if len(present_aliases) != len(aliases):
        return True
    if any(alias.printer_id is None for alias in present_aliases):
        return True
    return _duplicate_queue_alias_count(present_aliases) > 0


def _toner_values(printer: Printer) -> list[int]:
    if isinstance(printer.toner_levels, dict):
        return [
            int(value)
            for value in printer.toner_levels.values()
            if isinstance(value, (int, float)) and 0 <= int(value) <= 100
        ]
    if printer.toner_level is not None:
        return [printer.toner_level]
    return []


def _operational_health(db: Session, organization_id: int, now: datetime) -> dict:
    agents = db.query(PrintAgent).filter(PrintAgent.organization_id == organization_id).all()
    printers = db.query(Printer).filter(Printer.organization_id == organization_id, Printer.is_active.is_(True)).all()
    online_agents = sum(1 for agent in agents if _agent_is_online(agent, now))
    monitored_printers = sum(1 for printer in printers if printer.ip_address)
    low_toner_printers = sum(1 for printer in printers if any(value <= 10 for value in _toner_values(printer)))
    unbound_queues = (
        db.query(func.count(PrinterAlias.id))
        .filter(PrinterAlias.organization_id == organization_id, PrinterAlias.printer_id.is_(None))
        .scalar()
        or 0
    )
    usb_queues = (
        db.query(func.count(PrinterAlias.id))
        .filter(PrinterAlias.organization_id == organization_id, PrinterAlias.connection_type == "usb")
        .scalar()
        or 0
    )
    aliases_with_agent = (
        db.query(PrinterAlias)
        .filter(PrinterAlias.organization_id == organization_id, PrinterAlias.agent_id.isnot(None))
        .all()
    )
    duplicate_queue_aliases = _duplicate_queue_alias_count(aliases_with_agent)
    aliases_by_agent: dict[int, list[PrinterAlias]] = defaultdict(list)
    for alias in aliases_with_agent:
        if alias.agent_id is not None:
            aliases_by_agent[alias.agent_id].append(alias)
    agents_with_alerts = sum(1 for agent in agents if _agent_has_operational_alert(agent, aliases_by_agent.get(agent.id, []), now))

    return {
        "agents_total": len(agents),
        "agents_online": online_agents,
        "agents_offline": max(len(agents) - online_agents, 0),
        "agents_with_alerts": agents_with_alerts,
        "printers_total": len(printers),
        "printers_monitored": monitored_printers,
        "printers_unmonitored": max(len(printers) - monitored_printers, 0),
        "low_toner_printers": low_toner_printers,
        "unbound_queues": int(unbound_queues),
        "usb_queues": int(usb_queues),
        "duplicate_queue_aliases": duplicate_queue_aliases,
    }


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
        "operational_health": _operational_health(db, organization_id, now),
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
