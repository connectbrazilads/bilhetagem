from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.repositories.printers import create_printer
from app.schemas.printer import PrinterCreate, PrinterRead, PrinterStatusUpdate, PrinterUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/printers", tags=["printers"])


@router.get("", response_model=list[PrinterRead])
def list_printers(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[Printer]:
    return db.query(Printer).order_by(Printer.name).all()


@router.post("", response_model=PrinterRead, status_code=status.HTTP_201_CREATED)
def create_printer_endpoint(
    payload: PrinterCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Printer:
    try:
        printer = create_printer(db, payload)
        write_audit(db, action="printer_created", entity="printers", entity_id=printer.id, actor_user_id=actor.id)
        db.commit()
        db.refresh(printer)
        return printer
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Impressora já cadastrada") from exc


@router.put("/{printer_id}", response_model=PrinterRead)
def update_printer_endpoint(
    printer_id: int,
    payload: PrinterUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Printer:
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    
    if payload.name is not None:
        printer.name = payload.name
    if payload.location is not None:
        printer.location = payload.location
    if payload.is_color is not None:
        printer.is_color = payload.is_color
    if payload.cost_mono is not None:
        printer.cost_mono = payload.cost_mono
    if payload.cost_color is not None:
        printer.cost_color = payload.cost_color
    if payload.is_active is not None:
        printer.is_active = payload.is_active
    if payload.ip_address is not None:
        printer.ip_address = payload.ip_address if payload.ip_address.strip() != "" else None
        
    write_audit(db, action="printer_updated", entity="printers", entity_id=printer.id, actor_user_id=actor.id)
    db.commit()
    db.refresh(printer)
    return printer


@router.put("/{printer_id}/status", response_model=PrinterRead)
def update_printer_status_endpoint(
    printer_id: int,
    payload: PrinterStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
) -> Printer:
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora nÃ£o encontrada")

    printer.toner_level = payload.toner_level
    printer.toner_levels = payload.toner_levels
    printer.paper_status = payload.paper_status
    printer.serial_number = payload.serial_number
    printer.page_counter = payload.page_counter
    db.commit()
    db.refresh(printer)
    return printer
