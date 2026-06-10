from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.quota import Quota
from app.models.user import User, UserRole
from app.repositories.printers import create_printer
from app.schemas.printer import PrinterAliasBind, PrinterAliasRead, PrinterCreate, PrinterRead, PrinterStatusUpdate, PrinterUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/printers", tags=["printers"])


@router.get("", response_model=list[PrinterRead])
def list_printers(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.agent)),
) -> list[Printer]:
    return (
        db.query(Printer)
        .options(selectinload(Printer.aliases))
        .filter(Printer.organization_id == actor.organization_id)
        .order_by(Printer.name)
        .all()
    )


@router.post("", response_model=PrinterRead, status_code=status.HTTP_201_CREATED)
def create_printer_endpoint(
    payload: PrinterCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Printer:
    try:
        printer = create_printer(db, payload, actor.organization_id)
        write_audit(db, action="printer_created", entity="printers", entity_id=printer.id, actor_user_id=actor.id)
        db.commit()
        db.refresh(printer)
        return printer
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Impressora ja cadastrada") from exc


@router.put("/{printer_id}", response_model=PrinterRead)
def update_printer_endpoint(
    printer_id: int,
    payload: PrinterUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Printer:
    printer = db.query(Printer).filter(Printer.organization_id == actor.organization_id, Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora nao encontrada")
    
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
    actor: User = Depends(require_roles(UserRole.admin, UserRole.agent)),
) -> Printer:
    printer = db.query(Printer).filter(Printer.organization_id == actor.organization_id, Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora nao encontrada")

    printer.toner_level = payload.toner_level
    printer.toner_levels = payload.toner_levels
    printer.paper_status = payload.paper_status
    printer.serial_number = payload.serial_number
    printer.page_counter = payload.page_counter
    db.commit()
    db.refresh(printer)
    return printer


@router.put("/aliases/{alias_id}", response_model=PrinterAliasRead)
def bind_printer_alias_endpoint(
    alias_id: int,
    payload: PrinterAliasBind,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> PrinterAlias:
    alias = db.query(PrinterAlias).filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.id == alias_id).first()
    if not alias:
        raise HTTPException(status_code=404, detail="Fila/alias nao encontrada")

    target_printer = None
    if payload.printer_id is not None:
        target_printer = (
            db.query(Printer)
            .filter(Printer.organization_id == actor.organization_id, Printer.id == payload.printer_id)
            .first()
        )
        if not target_printer:
            raise HTTPException(status_code=404, detail="Impressora nao encontrada")

    alias.printer_id = target_printer.id if target_printer else None
    moved_jobs = 0
    if target_printer:
        moved_jobs = (
            db.query(PrintJob)
            .filter(PrintJob.organization_id == actor.organization_id, PrintJob.printer_alias_id == alias.id)
            .update({PrintJob.printer_id: target_printer.id}, synchronize_session=False)
        )

    write_audit(
        db,
        action="printer_alias_bound" if target_printer else "printer_alias_unbound",
        entity="printer_aliases",
        entity_id=alias.id,
        actor_user_id=actor.id,
        metadata={
            "queue_name": alias.queue_name,
            "printer_id": alias.printer_id,
            "moved_jobs": moved_jobs,
        },
    )
    db.commit()
    db.refresh(alias)
    return alias


@router.delete("/{printer_id}")
def delete_printer_endpoint(
    printer_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict[str, str | int]:
    printer = db.query(Printer).filter(Printer.organization_id == actor.organization_id, Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora nao encontrada")

    jobs = db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id, PrintJob.printer_id == printer.id).all()
    deleted_jobs = len(jobs)
    for job in jobs:
        if job.status not in (JobStatus.authorized, JobStatus.released):
            continue
        quota = (
            db.query(Quota)
            .filter(
                Quota.user_id == job.user_id,
                Quota.year == job.submitted_at.year,
                Quota.month == job.submitted_at.month,
            )
            .first()
        )
        if quota:
            quota.used_pages = max(quota.used_pages - job.pages, 0)
            quota.used_balance = max(quota.used_balance - job.cost, 0.0)

    for job in jobs:
        db.delete(job)
    db.query(PrinterAlias).filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.printer_id == printer.id).delete(synchronize_session=False)
    write_audit(
        db,
        action="printer_deleted",
        entity="printers",
        entity_id=printer.id,
        actor_user_id=actor.id,
        metadata={"printer": printer.name, "deleted_jobs": deleted_jobs},
    )
    db.delete(printer)
    db.commit()
    return {"status": "deleted", "deleted_jobs": deleted_jobs}


@router.post("/{source_printer_id}/merge/{target_printer_id}", response_model=PrinterRead)
def merge_printer_endpoint(
    source_printer_id: int,
    target_printer_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Printer:
    if source_printer_id == target_printer_id:
        raise HTTPException(status_code=400, detail="Impressoras devem ser diferentes")

    source = db.query(Printer).filter(Printer.organization_id == actor.organization_id, Printer.id == source_printer_id).first()
    target = db.query(Printer).filter(Printer.organization_id == actor.organization_id, Printer.id == target_printer_id).first()
    if not source or not target:
        raise HTTPException(status_code=404, detail="Impressora nao encontrada")

    moved_jobs = db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id, PrintJob.printer_id == source.id).update(
        {PrintJob.printer_id: target.id},
        synchronize_session=False,
    )
    moved_aliases = 0
    for alias in db.query(PrinterAlias).filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.printer_id == source.id).all():
        duplicate_alias = (
            db.query(PrinterAlias)
            .filter(
                PrinterAlias.printer_id == target.id,
                PrinterAlias.organization_id == actor.organization_id,
                PrinterAlias.agent_id == alias.agent_id,
                PrinterAlias.queue_name == alias.queue_name,
            )
            .first()
        )
        if duplicate_alias:
            db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id, PrintJob.printer_alias_id == alias.id).update(
                {PrintJob.printer_alias_id: duplicate_alias.id},
                synchronize_session=False,
            )
            db.delete(alias)
            continue
        alias.printer_id = target.id
        moved_aliases += 1

    if not target.ip_address and source.ip_address:
        target.ip_address = source.ip_address
    if not target.serial_number and source.serial_number:
        target.serial_number = source.serial_number
    if not target.location and source.location:
        target.location = source.location
    target.is_color = target.is_color or source.is_color

    write_audit(
        db,
        action="printer_merged",
        entity="printers",
        entity_id=target.id,
        actor_user_id=actor.id,
        metadata={
            "source_printer": source.name,
            "target_printer": target.name,
            "moved_jobs": moved_jobs,
            "moved_aliases": moved_aliases,
        },
    )
    db.delete(source)
    db.commit()
    db.refresh(target)
    return target
