from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy.orm import Session

from app.models.print_policy import PolicyAction, PolicyRuleType, PrintPolicy
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User
from app.schemas.job import PrintJobCreate


@dataclass(frozen=True)
class PolicyDecision:
    policy: PrintPolicy | None = None
    action: PolicyAction | None = None
    reason: str | None = None
    force_mono: bool = False


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _days_match(policy: PrintPolicy, submitted_at: datetime) -> bool:
    if not policy.days_of_week:
        return True
    tokens = {token.strip().lower() for token in policy.days_of_week.split(",") if token.strip()}
    if not tokens:
        return True
    names = {
        "mon": 0,
        "seg": 0,
        "tue": 1,
        "ter": 1,
        "wed": 2,
        "qua": 2,
        "thu": 3,
        "qui": 3,
        "fri": 4,
        "sex": 4,
        "sat": 5,
        "sab": 5,
        "sun": 6,
        "dom": 6,
    }
    allowed = set()
    for token in tokens:
        if token.isdigit():
            allowed.add(int(token))
        elif token[:3] in names:
            allowed.add(names[token[:3]])
    return submitted_at.weekday() in allowed


def _time_in_window(value: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


def _scope_matches(policy: PrintPolicy, payload: PrintJobCreate, user: User, printer: Printer, alias: PrinterAlias | None) -> bool:
    if policy.user_id is not None and policy.user_id != user.id:
        return False
    if policy.department_id is not None and policy.department_id != user.department_id:
        return False
    if policy.printer_id is not None and policy.printer_id != printer.id:
        return False
    if policy.printer_alias_id is not None and (not alias or policy.printer_alias_id != alias.id):
        return False
    if policy.queue_name:
        queue_name = _normalize(payload.queue_name or payload.printer_name)
        if _normalize(policy.queue_name) != queue_name:
            return False
    return True


def _rule_matches(policy: PrintPolicy, payload: PrintJobCreate) -> bool:
    if policy.rule_type == PolicyRuleType.always:
        return True
    if policy.rule_type == PolicyRuleType.max_pages:
        return policy.max_pages is not None and payload.pages > policy.max_pages
    if policy.rule_type == PolicyRuleType.color:
        return payload.is_color
    if policy.rule_type == PolicyRuleType.time_window:
        if not policy.start_time or not policy.end_time or not _days_match(policy, payload.submitted_at):
            return False
        return _time_in_window(payload.submitted_at.time(), policy.start_time, policy.end_time)
    return False


def _reason(policy: PrintPolicy) -> str:
    if policy.message:
        return policy.message
    if policy.action == PolicyAction.block:
        return f"Bloqueado pela politica: {policy.name}"
    if policy.action == PolicyAction.require_release:
        return f"Liberacao exigida pela politica: {policy.name}"
    if policy.action == PolicyAction.force_mono:
        return f"Convertido/cobrado como P&B pela politica: {policy.name}"
    return f"Permitido pela excecao: {policy.name}"


def evaluate_print_policies(
    db: Session,
    payload: PrintJobCreate,
    user: User,
    printer: Printer,
    alias: PrinterAlias | None,
    organization_id: int,
) -> PolicyDecision:
    policies = (
        db.query(PrintPolicy)
        .filter(PrintPolicy.organization_id == organization_id, PrintPolicy.is_active.is_(True))
        .order_by(PrintPolicy.priority, PrintPolicy.id)
        .all()
    )
    for policy in policies:
        if not _scope_matches(policy, payload, user, printer, alias):
            continue
        if not _rule_matches(policy, payload):
            continue
        if policy.action == PolicyAction.allow:
            return PolicyDecision(policy=policy, action=policy.action, reason=_reason(policy))
        return PolicyDecision(
            policy=policy,
            action=policy.action,
            reason=_reason(policy),
            force_mono=policy.action == PolicyAction.force_mono and payload.is_color,
        )
    return PolicyDecision()
