from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.printer import Printer


class PrinterLimitExceeded(ValueError):
    pass


def ensure_printer_limit_available(db: Session, organization_id: int) -> None:
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization or organization.contracted_printer_limit <= 0:
        return
    active_printers = (
        db.query(Printer.id)
        .filter(Printer.organization_id == organization_id, Printer.is_active.is_(True))
        .count()
    )
    if active_printers >= organization.contracted_printer_limit:
        raise PrinterLimitExceeded(
            f"Limite contratado de impressoras atingido ({active_printers}/{organization.contracted_printer_limit})"
        )
