from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias


@dataclass
class PrinterIdentityGroup:
    identity_type: str
    identity_value: str
    printer_ids: set[int] = field(default_factory=set)
    alias_ids: set[int] = field(default_factory=set)


def _identity_key(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def physical_identity_conflicts(db: Session, organization_id: int) -> list[PrinterIdentityGroup]:
    groups: dict[tuple[str, str], PrinterIdentityGroup] = {}

    def add_identity(identity_type: str, value: str | None, printer_id: int | None, alias_id: int | None = None) -> None:
        key_value = _identity_key(value)
        if not key_value or printer_id is None:
            return
        key = (identity_type, key_value)
        group = groups.setdefault(key, PrinterIdentityGroup(identity_type=identity_type, identity_value=key_value))
        group.printer_ids.add(printer_id)
        if alias_id is not None:
            group.alias_ids.add(alias_id)

    printers = db.query(Printer).filter(Printer.organization_id == organization_id, Printer.is_active.is_(True)).all()
    for printer in printers:
        add_identity("serial", printer.serial_number, printer.id)
        add_identity("ip", printer.ip_address, printer.id)

    aliases = (
        db.query(PrinterAlias)
        .join(Printer, Printer.id == PrinterAlias.printer_id)
        .filter(PrinterAlias.organization_id == organization_id, PrinterAlias.printer_id.isnot(None))
        .filter(Printer.is_active.is_(True))
        .all()
    )
    for alias in aliases:
        add_identity("serial", alias.serial_number, alias.printer_id, alias.id)
        add_identity("ip", alias.ip_address, alias.printer_id, alias.id)
        add_identity("device", alias.device_id, alias.printer_id, alias.id)
        add_identity("fingerprint", alias.fingerprint, alias.printer_id, alias.id)

    return [group for group in groups.values() if len(group.printer_ids) > 1]


def conflicting_alias_ids(db: Session, organization_id: int) -> set[int]:
    alias_ids: set[int] = set()
    for group in physical_identity_conflicts(db, organization_id):
        alias_ids.update(group.alias_ids)
    return alias_ids
