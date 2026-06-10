from sqlalchemy.orm import Session

from app.models.printer import Printer
from app.schemas.printer import PrinterCreate
from app.services.printer_limit_service import ensure_printer_limit_available
from app.services.settings_service import get_system_settings_dict


def create_printer(db: Session, payload: PrinterCreate, organization_id: int) -> Printer:
    ensure_printer_limit_available(db, organization_id)
    settings = get_system_settings_dict(db, organization_id)
    printer = Printer(
        organization_id=organization_id,
        name=payload.name,
        location=payload.location,
        is_color=payload.is_color,
        cost_mono=payload.cost_mono if payload.cost_mono is not None else settings["default_printer_cost_mono"],
        cost_color=payload.cost_color if payload.cost_color is not None else settings["default_printer_cost_color"],
        ip_address=payload.ip_address,
    )
    db.add(printer)
    db.flush()
    return printer
