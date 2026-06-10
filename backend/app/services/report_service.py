from datetime import datetime, time, timedelta, timezone
from collections import defaultdict
import unicodedata

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.agent_queue_action import AgentQueueAction, AgentQueueActionStatus
from app.models.agent_log import AgentLog
from app.models.print_agent import PrintAgent
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User
from app.services.agent_release_service import is_newer_version, published_agent_update_version
from app.services.organization_contract_service import printer_contract_overview
from app.services.printer_identity_service import physical_identity_conflicts

AGENT_ONLINE_WINDOW = timedelta(minutes=3)
QUEUE_ACTION_STALE_AFTER = timedelta(minutes=15)
RECENT_AGENT_LOG_ALERT_WINDOW = timedelta(minutes=15)


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


def _plain_text_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKD", value.strip())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(ascii_text.lower().split()) or None


def _is_generic_queue_name(value: str | None) -> bool:
    return _plain_text_key(value) in {
        "documento de impressao",
        "print document",
        "user",
        "unknown",
    }


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


def _queue_action_is_stale(action: AgentQueueAction, now: datetime) -> bool:
    if action.status not in (AgentQueueActionStatus.pending, AgentQueueActionStatus.running):
        return False
    reference = action.dispatched_at if action.status == AgentQueueActionStatus.running else action.requested_at
    if reference is None:
        return False
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return now - reference > QUEUE_ACTION_STALE_AFTER


def _agent_has_operational_alert(
    agent: PrintAgent,
    aliases: list[PrinterAlias],
    queue_actions: list[AgentQueueAction],
    has_recent_error_log: bool,
    latest_agent_version: str | None,
    now: datetime,
) -> bool:
    if not _agent_is_online(agent, now):
        return True
    if agent.last_error or agent.event_log_enabled is False or agent.local_admin is False:
        return True
    if latest_agent_version and is_newer_version(latest_agent_version, agent.version):
        return True
    if has_recent_error_log:
        return True
    if any(_queue_action_is_stale(action, now) for action in queue_actions):
        return True

    present_aliases = [alias for alias in aliases if _alias_is_present(agent, alias)]
    if agent.last_seen_at and not present_aliases:
        return True
    if len(present_aliases) != len(aliases):
        return True
    if any(alias.printer_id is None for alias in present_aliases):
        return True
    if _duplicate_queue_alias_count(present_aliases) > 0:
        return True
    return any(_is_generic_queue_name(alias.queue_name) for alias in present_aliases)


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
    agents_without_local_admin = sum(1 for agent in agents if agent.local_admin is False)
    agents_without_event_log = sum(1 for agent in agents if agent.event_log_enabled is False)
    monitored_printers = sum(1 for printer in printers if printer.ip_address)
    low_toner_printers = sum(1 for printer in printers if any(value <= 10 for value in _toner_values(printer)))
    aliases_with_agent = (
        db.query(PrinterAlias)
        .filter(PrinterAlias.organization_id == organization_id, PrinterAlias.agent_id.isnot(None))
        .all()
    )
    aliases_by_agent: dict[int, list[PrinterAlias]] = defaultdict(list)
    for alias in aliases_with_agent:
        if alias.agent_id is not None:
            aliases_by_agent[alias.agent_id].append(alias)
    present_aliases = [
        alias
        for agent in agents
        for alias in aliases_by_agent.get(agent.id, [])
        if _alias_is_present(agent, alias)
    ]
    unbound_queues = sum(1 for alias in present_aliases if alias.printer_id is None)
    usb_queues = sum(1 for alias in present_aliases if alias.connection_type == "usb")
    duplicate_queue_aliases = _duplicate_queue_alias_count(present_aliases)
    generic_queue_aliases = sum(1 for alias in present_aliases if _is_generic_queue_name(alias.queue_name))
    hardware_identity_conflicts = len(physical_identity_conflicts(db, organization_id))
    pending_queue_actions = (
        db.query(AgentQueueAction)
        .filter(
            AgentQueueAction.organization_id == organization_id,
            AgentQueueAction.status.in_([AgentQueueActionStatus.pending, AgentQueueActionStatus.running]),
        )
        .all()
    )
    queue_actions_by_agent: dict[int, list[AgentQueueAction]] = defaultdict(list)
    for action in pending_queue_actions:
        queue_actions_by_agent[action.agent_id].append(action)
    stale_queue_actions = sum(1 for action in pending_queue_actions if _queue_action_is_stale(action, now))
    recent_log_cutoff = now - RECENT_AGENT_LOG_ALERT_WINDOW
    recent_error_agent_ids = {
        int(row[0])
        for row in (
            db.query(AgentLog.agent_id)
            .filter(
                AgentLog.organization_id == organization_id,
                AgentLog.received_at >= recent_log_cutoff,
                AgentLog.level.in_(["error", "critical"]),
            )
            .distinct()
            .all()
        )
    }
    agents_with_recent_errors = len(recent_error_agent_ids)
    latest_agent_version = published_agent_update_version()
    outdated_agents = sum(1 for agent in agents if latest_agent_version and is_newer_version(latest_agent_version, agent.version))
    agents_with_alerts = sum(
        1
        for agent in agents
        if _agent_has_operational_alert(
            agent,
            aliases_by_agent.get(agent.id, []),
            queue_actions_by_agent.get(agent.id, []),
            agent.id in recent_error_agent_ids,
            latest_agent_version,
            now,
        )
    )

    return {
        "agents_total": len(agents),
        "agents_online": online_agents,
        "agents_offline": max(len(agents) - online_agents, 0),
        "agents_with_alerts": agents_with_alerts,
        "agents_without_local_admin": agents_without_local_admin,
        "agents_without_event_log": agents_without_event_log,
        "outdated_agents": outdated_agents,
        "agents_with_recent_errors": agents_with_recent_errors,
        "printers_total": len(printers),
        "printers_monitored": monitored_printers,
        "printers_unmonitored": max(len(printers) - monitored_printers, 0),
        "low_toner_printers": low_toner_printers,
        "unbound_queues": int(unbound_queues),
        "usb_queues": int(usb_queues),
        "duplicate_queue_aliases": duplicate_queue_aliases,
        "generic_queue_aliases": int(generic_queue_aliases),
        "hardware_identity_conflicts": int(hardware_identity_conflicts),
        "pending_queue_actions": len(pending_queue_actions),
        "stale_queue_actions": int(stale_queue_actions),
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
    cost_center_usage = [
        {
            "cost_center": cost_center or "Sem centro de custo",
            "pages": int(pages or 0),
            "cost": _round_money(cost),
            "cost_per_page": _cost_per_page(cost, int(pages or 0)),
        }
        for cost_center, pages, cost in db.query(
            Department.cost_center,
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
        .group_by(Department.cost_center)
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
        "contract_overview": printer_contract_overview(db, organization_id),
        "operational_health": _operational_health(db, organization_id, now),
        "top_users": top_users,
        "top_printers": top_printers,
        "department_usage": department_usage,
        "cost_center_usage": cost_center_usage,
        "color_usage": color_usage,
        "eco_metrics": {
            "pages_saved": pages_saved_month,
            "co2_saved_g": co2_saved,
            "water_saved_l": water_saved,
            "trees_saved": trees_saved
        }
    }
