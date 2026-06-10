import unicodedata

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.print_agent import PrintAgent
from app.models.print_job import JobStatus, PrintJob
from app.models.print_policy import PolicyAction
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate, PrintJobDecision
from app.services.audit_service import write_audit
from app.services.organization_service import get_or_create_default_organization
from app.services.policy_service import PolicyDecision, evaluate_print_policies
from app.services.printer_limit_service import ensure_printer_limit_available
from app.services.quota_service import can_consume, get_or_create_current_quota


def _resolve_organization_id(db: Session, organization_id: int | None) -> int:
    return organization_id or get_or_create_default_organization(db).id


def _resolve_user(db: Session, username: str, auto_create_users: bool, organization_id: int) -> User:
    username = _normalize_username(username)
    user = db.query(User).filter(User.organization_id == organization_id, User.username == username).first()
    if user:
        return user
    if not auto_create_users:
        raise ValueError(f"Usuario '{username}' nao cadastrado")
    user = User(organization_id=organization_id, username=username, full_name=username, role=UserRole.user, is_active=True)
    db.add(user)
    db.flush()
    return user


def _normalize_username(username: str) -> str:
    normalized = username.strip()
    if "\\" in normalized:
        normalized = normalized.rsplit("\\", 1)[-1]
    if "@" in normalized:
        normalized = normalized.split("@", 1)[0]
    return "_".join(normalized.strip().lower().split()) or "unknown"


def _resolve_printer(db: Session, printer_name: str, is_color: bool, organization_id: int, sys_settings: dict | None = None) -> Printer:
    printer = db.query(Printer).filter(Printer.organization_id == organization_id, Printer.name == printer_name).first()
    if printer:
        return printer
    if not settings.auto_create_printers:
        raise ValueError(f"Impressora '{printer_name}' nao cadastrada")
    ensure_printer_limit_available(db, organization_id)
    sys_settings = sys_settings or {}
    printer = Printer(
        organization_id=organization_id,
        name=printer_name,
        is_color=is_color,
        cost_mono=float(sys_settings.get("default_printer_cost_mono", 0.05)),
        cost_color=float(sys_settings.get("default_printer_cost_color", 0.25)),
    )
    db.add(printer)
    db.flush()
    return printer


def _normalize_alias_name(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _identity_key(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    return cleaned.lower() if cleaned else None


def _plain_text_key(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    if not cleaned:
        return None
    normalized = unicodedata.normalize("NFKD", cleaned)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(ascii_text.lower().split()) or None


def _is_generic_printer_name(value: str | None) -> bool:
    return _plain_text_key(value) in {
        "documento de impressao",
        "print document",
        "user",
        "unknown",
    }


def _same_identity(left: str | None, right: str | None) -> bool:
    left_key = _identity_key(left)
    right_key = _identity_key(right)
    return bool(left_key and right_key and left_key == right_key)


def _find_printer_by_serial(db: Session, organization_id: int, serial_number: str | None) -> Printer | None:
    identity = _identity_key(serial_number)
    if not identity:
        return None
    return (
        db.query(Printer)
        .filter(
            Printer.organization_id == organization_id,
            Printer.serial_number.isnot(None),
            func.lower(Printer.serial_number) == identity,
        )
        .first()
    )


def _find_bound_alias_by_identity(db: Session, organization_id: int, column, value: str | None) -> PrinterAlias | None:
    identity = _identity_key(value)
    if not identity:
        return None
    return (
        db.query(PrinterAlias)
        .filter(
            PrinterAlias.organization_id == organization_id,
            PrinterAlias.printer_id.isnot(None),
            column.isnot(None),
            func.lower(column) == identity,
        )
        .first()
    )


def _find_single_bound_agent_printer(db: Session, organization_id: int, agent: PrintAgent | None) -> Printer | None:
    if not agent:
        return None
    aliases = (
        db.query(PrinterAlias)
        .filter(
            PrinterAlias.organization_id == organization_id,
            PrinterAlias.agent_id == agent.id,
            PrinterAlias.printer_id.isnot(None),
        )
        .all()
    )
    printer_ids = {alias.printer_id for alias in aliases if alias.printer_id is not None}
    if len(printer_ids) != 1:
        return None
    return aliases[0].printer


def _policy_audit_metadata(policy_decision: PolicyDecision, requested_is_color: bool, effective_is_color: bool) -> dict:
    if not policy_decision.policy:
        return {
            "policy_applied": False,
            "requested_is_color": requested_is_color,
            "effective_is_color": effective_is_color,
        }
    return {
        "policy_applied": True,
        "policy_id": policy_decision.policy.id,
        "policy_name": policy_decision.policy.name,
        "policy_action": policy_decision.action.value if policy_decision.action else None,
        "policy_reason": policy_decision.reason,
        "policy_force_mono": policy_decision.force_mono,
        "requested_is_color": requested_is_color,
        "effective_is_color": effective_is_color,
    }


def _upsert_agent(db: Session, payload: PrintJobCreate, organization_id: int) -> PrintAgent | None:
    agent_uid = _clean_optional(payload.agent_uid)
    if not agent_uid:
        return None
    from datetime import datetime, timezone

    agent = db.query(PrintAgent).filter(PrintAgent.organization_id == organization_id, PrintAgent.agent_uid == agent_uid).first()
    if not agent:
        agent = PrintAgent(organization_id=organization_id, agent_uid=agent_uid)
        db.add(agent)
        db.flush()
    agent.computer_name = _clean_optional(payload.computer_name)
    agent.last_seen_at = datetime.now(timezone.utc)
    return agent


def _find_existing_printer(db: Session, payload: PrintJobCreate, agent: PrintAgent | None, organization_id: int) -> Printer | None:
    serial = _clean_optional(payload.printer_serial)
    if serial:
        printer = _find_printer_by_serial(db, organization_id, serial)
        if printer:
            return printer
        alias = _find_bound_alias_by_identity(db, organization_id, PrinterAlias.serial_number, serial)
        if alias and alias.printer:
            return alias.printer

    ip_address = _clean_optional(payload.printer_ip_address)
    if ip_address:
        printer = db.query(Printer).filter(Printer.organization_id == organization_id, Printer.ip_address == ip_address).first()
        if printer:
            return printer
        alias = (
            db.query(PrinterAlias)
            .filter(
                PrinterAlias.organization_id == organization_id,
                PrinterAlias.ip_address == ip_address,
                PrinterAlias.printer_id.isnot(None),
            )
            .first()
        )
        if alias and alias.printer:
            return alias.printer

    queue_name = _clean_optional(payload.queue_name) or payload.printer_name
    if agent and queue_name:
        normalized_queue_name = _normalize_alias_name(queue_name)
        alias = (
            db.query(PrinterAlias)
            .filter(
                PrinterAlias.organization_id == organization_id,
                PrinterAlias.agent_id == agent.id,
                or_(
                    PrinterAlias.queue_name == queue_name,
                    PrinterAlias.normalized_queue_name == normalized_queue_name,
                ),
            )
            .first()
        )
        if alias and alias.printer:
            return alias.printer

    device_id = _clean_optional(payload.printer_device_id)
    if device_id:
        alias = _find_bound_alias_by_identity(db, organization_id, PrinterAlias.device_id, device_id)
        if alias and alias.printer:
            return alias.printer

    fingerprint = _clean_optional(payload.printer_fingerprint)
    if fingerprint:
        alias = _find_bound_alias_by_identity(db, organization_id, PrinterAlias.fingerprint, fingerprint)
        if alias and alias.printer:
            return alias.printer

    if _is_generic_printer_name(payload.printer_name) or _is_generic_printer_name(payload.queue_name):
        printer = _find_single_bound_agent_printer(db, organization_id, agent)
        if printer:
            return printer

    return db.query(Printer).filter(Printer.organization_id == organization_id, Printer.name == payload.printer_name).first()


def _resolve_printer_for_job(
    db: Session,
    payload: PrintJobCreate,
    agent: PrintAgent | None,
    organization_id: int,
    sys_settings: dict | None = None,
) -> Printer:
    printer = _find_existing_printer(db, payload, agent, organization_id)
    if printer:
        if payload.printer_serial and not printer.serial_number:
            printer.serial_number = payload.printer_serial
        if payload.printer_ip_address and not printer.ip_address:
            printer.ip_address = payload.printer_ip_address
        elif payload.printer_ip_address and _same_identity(printer.serial_number, payload.printer_serial):
            printer.ip_address = payload.printer_ip_address
        return printer
    return _resolve_printer(db, payload.printer_name, payload.is_color, organization_id, sys_settings)


def _upsert_printer_alias(db: Session, payload: PrintJobCreate, agent: PrintAgent | None, printer: Printer, organization_id: int) -> PrinterAlias | None:
    queue_name = _clean_optional(payload.queue_name) or payload.printer_name
    if not queue_name:
        return None
    from datetime import datetime, timezone

    alias = None
    if agent:
        normalized_queue_name = _normalize_alias_name(queue_name)
        alias = (
            db.query(PrinterAlias)
            .filter(
                PrinterAlias.organization_id == organization_id,
                PrinterAlias.agent_id == agent.id,
                or_(
                    PrinterAlias.queue_name == queue_name,
                    PrinterAlias.normalized_queue_name == normalized_queue_name,
                ),
            )
            .first()
        )
    if alias is None and not agent and payload.printer_fingerprint:
        fingerprint_identity = _identity_key(payload.printer_fingerprint)
        if fingerprint_identity:
            alias = (
                db.query(PrinterAlias)
                .filter(
                    PrinterAlias.organization_id == organization_id,
                    PrinterAlias.fingerprint.isnot(None),
                    func.lower(PrinterAlias.fingerprint) == fingerprint_identity,
                )
                .first()
            )
    if alias is None:
        alias = PrinterAlias(organization_id=organization_id, agent_id=agent.id if agent else None, queue_name=queue_name)
        db.add(alias)
        db.flush()

    alias.printer_id = printer.id
    alias.normalized_queue_name = _normalize_alias_name(queue_name)
    alias.computer_name = _clean_optional(payload.computer_name)
    alias.driver_name = _clean_optional(payload.printer_driver_name)
    alias.port_name = _clean_optional(payload.printer_port_name)
    alias.connection_type = _clean_optional(payload.printer_connection_type)
    alias.ip_address = _clean_optional(payload.printer_ip_address)
    alias.serial_number = _clean_optional(payload.printer_serial)
    alias.device_id = _clean_optional(payload.printer_device_id)
    alias.fingerprint = _clean_optional(payload.printer_fingerprint)
    alias.last_seen_at = datetime.now(timezone.utc)
    return alias


def register_print_job(db: Session, payload: PrintJobCreate, organization_id: int | None = None) -> PrintJobDecision:
    from app.services.settings_service import get_system_settings_dict
    organization_id = _resolve_organization_id(db, organization_id)
    sys_settings = get_system_settings_dict(db, organization_id)

    user = _resolve_user(db, payload.username, sys_settings["auto_create_users"], organization_id)
    agent = _upsert_agent(db, payload, organization_id)
    printer = _resolve_printer_for_job(db, payload, agent, organization_id, sys_settings)
    alias = _upsert_printer_alias(db, payload, agent, printer, organization_id)
    policy_decision = evaluate_print_policies(db, payload, user, printer, alias, organization_id)
    quota = get_or_create_current_quota(db, user, payload.submitted_at)
    is_print_event_log_job = bool(payload.external_job_id and payload.external_job_id.startswith("eventlog:"))

    if payload.external_job_id:
        existing_job = (
            db.query(PrintJob)
            .filter(
                PrintJob.printer_id == printer.id,
                PrintJob.organization_id == organization_id,
                PrintJob.external_job_id == payload.external_job_id,
            )
            .order_by(PrintJob.id.desc())
            .first()
        )
        if existing_job:
            return PrintJobDecision(
                job_id=existing_job.id,
                status=existing_job.status,
                authorized=existing_job.status in (JobStatus.authorized, JobStatus.pending_release, JobStatus.released),
                remaining_pages=quota.remaining_pages,
                remaining_balance=quota.remaining_balance,
                reason=existing_job.reason,
                policy_name=existing_job.policy_name,
                policy_action=existing_job.policy_action,
            )

    effective_is_color = payload.is_color and not policy_decision.force_mono
    cost = payload.pages * (printer.cost_color if effective_is_color else printer.cost_mono)

    # Calculate total cost/pages of currently pending release jobs for this user to prevent double-spending
    import sqlalchemy as sa
    pending_cost = db.query(sa.func.sum(PrintJob.cost)).filter(
        PrintJob.user_id == user.id,
        PrintJob.organization_id == organization_id,
        PrintJob.status == JobStatus.pending_release
    ).scalar() or 0.0
    pending_pages = db.query(sa.func.sum(PrintJob.pages)).filter(
        PrintJob.user_id == user.id,
        PrintJob.organization_id == organization_id,
        PrintJob.status == JobStatus.pending_release
    ).scalar() or 0

    # Validate against effective pages and balance (subtracting pending ones)
    effective_remaining_pages = quota.remaining_pages - pending_pages
    effective_remaining_balance = quota.remaining_balance - pending_cost

    authorized_pages = effective_remaining_pages >= payload.pages
    authorized_balance = effective_remaining_balance >= cost

    policy_blocks = policy_decision.action == PolicyAction.block
    if policy_blocks:
        authorized = False
    elif sys_settings["blocking_enabled"]:
        authorized = authorized_pages and authorized_balance
    else:
        authorized = True

    reason = policy_decision.reason if policy_decision.action in (PolicyAction.block, PolicyAction.force_mono) else None
    if policy_blocks:
        status = JobStatus.blocked
        reason = policy_decision.reason
    elif not authorized:
        status = JobStatus.blocked
        if not authorized_pages:
            reason = "Cota de paginas insuficiente (fila de liberacao inclusa)"
        else:
            reason = "Saldo mensal insuficiente (fila de liberacao inclusa)"
    else:
        policy_requires_release = policy_decision.action == PolicyAction.require_release
        if policy_requires_release and is_print_event_log_job:
            status = JobStatus.authorized
            reason = policy_decision.reason
            quota.used_pages += payload.pages
            quota.used_balance += cost
        elif (sys_settings["safe_release_enabled"] or policy_requires_release) and not is_print_event_log_job:
            status = JobStatus.pending_release
            reason = policy_decision.reason if policy_requires_release else None
        else:
            status = JobStatus.authorized
            quota.used_pages += payload.pages
            quota.used_balance += cost

    job = PrintJob(
        organization_id=organization_id,
        user_id=user.id,
        printer_id=printer.id,
        printer_alias_id=alias.id if alias else None,
        agent_id=agent.id if agent else None,
        external_job_id=payload.external_job_id,
        document_name=payload.document_name,
        computer_name=payload.computer_name,
        queue_name=payload.queue_name or payload.printer_name,
        pages=payload.pages,
        is_color=effective_is_color,
        cost=cost,
        status=status,
        reason=reason,
        policy_id=policy_decision.policy.id if policy_decision.policy else None,
        policy_name=policy_decision.policy.name if policy_decision.policy else None,
        policy_action=policy_decision.action.value if policy_decision.action else None,
        submitted_at=payload.submitted_at,
    )
    db.add(job)
    db.flush()
    write_audit(
        db,
        action="print_job_authorized" if authorized else "print_job_blocked",
        entity="print_jobs",
        entity_id=job.id,
        metadata={
            "username": user.username,
            "printer": printer.name,
            "pages": payload.pages,
            "remaining_pages": quota.remaining_pages,
            "cost": cost,
            "remaining_balance": quota.remaining_balance,
            **_policy_audit_metadata(policy_decision, payload.is_color, effective_is_color),
        },
        organization_id=organization_id,
    )
    db.commit()
    db.refresh(job)
    return PrintJobDecision(
        job_id=job.id,
        status=status,
        authorized=authorized,
        remaining_pages=quota.remaining_pages,
        remaining_balance=quota.remaining_balance,
        reason=reason,
        policy_name=job.policy_name,
        policy_action=job.policy_action,
    )
