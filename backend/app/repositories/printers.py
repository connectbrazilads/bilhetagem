from sqlalchemy.orm import Session

from app.models.printer import Printer
from app.schemas.printer import PrinterCreate


def create_printer(db: Session, payload: PrinterCreate, organization_id: int) -> Printer:
    printer = Printer(
        organization_id=organization_id,
        name=payload.name,
        location=payload.location,
        is_color=payload.is_color,
        cost_mono=payload.cost_mono,
        cost_color=payload.cost_color,
        ip_address=payload.ip_address,
    )
    db.add(printer)
    db.flush()
    return printer
