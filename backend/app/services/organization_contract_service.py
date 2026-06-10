from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.printer import Printer

CONTRACT_OVERVIEW_KEYS = (
    "billing_plan",
    "billing_status",
    "contracted_printer_limit",
    "active_printers_count",
    "printer_usage_percent",
    "printer_limit_status",
)


def printer_limit_status(active_printers: int, limit: int) -> tuple[float, str]:
    if limit <= 0:
        return 0.0, "unlimited"
    usage_percent = round((active_printers / limit) * 100, 1)
    if active_printers > limit:
        return usage_percent, "exceeded"
    if usage_percent >= 80:
        return usage_percent, "warning"
    return usage_percent, "ok"


def active_printers_count(db: Session, organization_id: int) -> int:
    return (
        db.query(Printer)
        .filter(Printer.organization_id == organization_id, Printer.is_active.is_(True))
        .count()
    )


def printer_contract_summary(db: Session, organization_id: int) -> dict:
    organization = db.get(Organization, organization_id)
    printers_count = db.query(Printer).filter(Printer.organization_id == organization_id).count()
    active_printers = active_printers_count(db, organization_id)
    contracted_limit = organization.contracted_printer_limit if organization else 0
    usage_percent, limit_status = printer_limit_status(active_printers, contracted_limit)
    return {
        "organization_name": organization.name if organization else "",
        "organization_slug": organization.slug if organization else "",
        "billing_plan": organization.billing_plan if organization else "starter",
        "billing_status": organization.billing_status if organization else "trial",
        "contracted_printer_limit": contracted_limit,
        "printers_count": printers_count,
        "active_printers_count": active_printers,
        "printer_usage_percent": usage_percent,
        "printer_limit_status": limit_status,
    }


def printer_contract_overview(db: Session, organization_id: int) -> dict:
    summary = printer_contract_summary(db, organization_id)
    return {key: summary[key] for key in CONTRACT_OVERVIEW_KEYS}
