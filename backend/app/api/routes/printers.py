from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.agent_queue_action import AgentQueueAction, AgentQueueActionStatus
from app.models.print_agent import PrintAgent
from app.models.print_job import PrintJob
from app.models.print_policy import PrintPolicy
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User, UserRole
from app.repositories.printers import create_printer
from app.schemas.printer import PrinterAliasBind, PrinterAliasRead, PrinterCreate, PrinterRead, PrinterStatusUpdate, PrinterUpdate
from app.services.audit_service import write_audit
from app.services.printer_limit_service import PrinterLimitExceeded, ensure_printer_limit_available
from app.services.printer_identity_service import physical_identity_conflicts

router = APIRouter(prefix="/printers", tags=["printers"])


def _changed_values(before: dict, after: dict) -> dict:
    return {
        key: {"before": before_value, "after": after[key]}
        for key, before_value in before.items()
        if before_value != after[key]
    }


def _normalize_alias_name(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _same_alias_identity(left: PrinterAlias, right: PrinterAlias) -> bool:
    if left.queue_name == right.queue_name:
        return True
    left_normalized = left.normalized_queue_name or _normalize_alias_name(left.queue_name)
    right_normalized = right.normalized_queue_name or _normalize_alias_name(right.queue_name)
    return bool(left_normalized and left_normalized == right_normalized)


def _ensure_agent_can_update_printer_status(db: Session, actor: User, printer_id: int, agent_uid: str | None) -> None:
    if actor.role != UserRole.agent:
        return
    cleaned_agent_uid = (agent_uid or "").strip()
    if not cleaned_agent_uid:
        raise HTTPException(status_code=403, detail="agent_uid obrigatorio para atualizar status da impressora")
    agent = (
        db.query(PrintAgent)
        .filter(PrintAgent.organization_id == actor.organization_id, PrintAgent.agent_uid == cleaned_agent_uid)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=403, detail="Agent nao autorizado para atualizar esta impressora")
    alias = (
        db.query(PrinterAlias.id)
        .filter(
            PrinterAlias.organization_id == actor.organization_id,
            PrinterAlias.agent_id == agent.id,
            PrinterAlias.printer_id == printer_id,
        )
        .first()
    )
    if not alias:
        raise HTTPException(status_code=403, detail="Agent nao possui fila vinculada a esta impressora")


def _annotate_identity_conflicts(db: Session, organization_id: int, printers: list[Printer]) -> list[Printer]:
    conflict_types: dict[int, set[str]] = {printer.id: set() for printer in printers}
    conflict_printer_ids: dict[int, set[int]] = {printer.id: set() for printer in printers}
    known_printer_ids = set(conflict_types)

    for group in physical_identity_conflicts(db, organization_id):
        involved_ids = group.printer_ids & known_printer_ids
        if not involved_ids:
            continue
        for printer_id in involved_ids:
            conflict_types[printer_id].add(group.identity_type)
            conflict_printer_ids[printer_id].update(group.printer_ids - {printer_id})

    for printer in printers:
        types = sorted(conflict_types.get(printer.id, set()))
        related_ids = sorted(conflict_printer_ids.get(printer.id, set()))
        printer.identity_conflict_count = len(types)
        printer.identity_conflict_types = types
        printer.identity_conflict_printer_ids = related_ids
    return printers


@router.get("", response_model=list[PrinterRead])
def list_printers(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.agent)),
) -> list[Printer]:
    printers = (
        db.query(Printer)
        .options(selectinload(Printer.aliases))
        .filter(Printer.organization_id == actor.organization_id)
        .order_by(Printer.name)
        .all()
    )
    return _annotate_identity_conflicts(db, actor.organization_id, printers)


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
    except PrinterLimitExceeded as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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

    if payload.is_active is True and not printer.is_active:
        try:
            ensure_printer_limit_available(db, actor.organization_id)
        except PrinterLimitExceeded as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    before = {
        "name": printer.name,
        "location": printer.location,
        "is_color": printer.is_color,
        "cost_mono": printer.cost_mono,
        "cost_color": printer.cost_color,
        "is_active": printer.is_active,
        "ip_address": printer.ip_address,
    }
    
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

    after = {
        "name": printer.name,
        "location": printer.location,
        "is_color": printer.is_color,
        "cost_mono": printer.cost_mono,
        "cost_color": printer.cost_color,
        "is_active": printer.is_active,
        "ip_address": printer.ip_address,
    }
    changes = _changed_values(before, after)
    if changes:
        write_audit(
            db,
            action="printer_updated",
            entity="printers",
            entity_id=printer.id,
            actor_user_id=actor.id,
            metadata={"changes": changes},
        )
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
    _ensure_agent_can_update_printer_status(db, actor, printer.id, payload.agent_uid)

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

    job_count = db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id, PrintJob.printer_id == printer.id).count()
    if job_count:
        raise HTTPException(
            status_code=409,
            detail="Impressora possui historico de impressoes. Desative ou mescle a impressora para preservar relatorios e auditoria.",
        )

    alias_ids = [
        alias_id
        for (alias_id,) in db.query(PrinterAlias.id)
        .filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.printer_id == printer.id)
        .all()
    ]
    policy_filters = [PrintPolicy.printer_id == printer.id]
    if alias_ids:
        policy_filters.append(PrintPolicy.printer_alias_id.in_(alias_ids))
    policy_count = (
        db.query(PrintPolicy)
        .filter(
            PrintPolicy.organization_id == actor.organization_id,
            or_(*policy_filters),
        )
        .count()
    )
    if policy_count:
        raise HTTPException(
            status_code=409,
            detail="Impressora possui politicas vinculadas. Remova, edite ou mescle a impressora para preservar as regras comerciais.",
        )

    active_queue_actions = (
        db.query(AgentQueueAction)
        .filter(
            AgentQueueAction.organization_id == actor.organization_id,
            AgentQueueAction.printer_id == printer.id,
            AgentQueueAction.status.in_([AgentQueueActionStatus.pending, AgentQueueActionStatus.running]),
        )
        .count()
    )
    if active_queue_actions:
        raise HTTPException(
            status_code=409,
            detail="Impressora possui acoes remotas pendentes ou em execucao. Cancele ou aguarde a conclusao antes de excluir.",
        )

    detached_queue_actions = (
        db.query(AgentQueueAction)
        .filter(AgentQueueAction.organization_id == actor.organization_id, AgentQueueAction.printer_id == printer.id)
        .update({AgentQueueAction.printer_id: None}, synchronize_session=False)
    )

    db.query(PrinterAlias).filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.printer_id == printer.id).delete(synchronize_session=False)
    write_audit(
        db,
        action="printer_deleted",
        entity="printers",
        entity_id=printer.id,
        actor_user_id=actor.id,
        metadata={"printer": printer.name, "deleted_jobs": 0, "detached_queue_actions": detached_queue_actions},
    )
    db.delete(printer)
    db.commit()
    return {"status": "deleted", "deleted_jobs": 0, "detached_queue_actions": detached_queue_actions}


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
    moved_policies = db.query(PrintPolicy).filter(PrintPolicy.organization_id == actor.organization_id, PrintPolicy.printer_id == source.id).update(
        {PrintPolicy.printer_id: target.id},
        synchronize_session=False,
    )
    moved_aliases = 0
    merged_aliases = 0
    moved_alias_policies = 0
    for alias in db.query(PrinterAlias).filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.printer_id == source.id).all():
        target_aliases = (
            db.query(PrinterAlias)
            .filter(
                PrinterAlias.printer_id == target.id,
                PrinterAlias.organization_id == actor.organization_id,
                PrinterAlias.agent_id == alias.agent_id,
            )
            .all()
        )
        duplicate_alias = next((candidate for candidate in target_aliases if _same_alias_identity(alias, candidate)), None)
        if duplicate_alias:
            moved_alias_policies += db.query(PrintPolicy).filter(PrintPolicy.organization_id == actor.organization_id, PrintPolicy.printer_alias_id == alias.id).update(
                {PrintPolicy.printer_alias_id: duplicate_alias.id},
                synchronize_session=False,
            )
            db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id, PrintJob.printer_alias_id == alias.id).update(
                {PrintJob.printer_alias_id: duplicate_alias.id},
                synchronize_session=False,
            )
            db.delete(alias)
            merged_aliases += 1
            continue
        alias.printer_id = target.id
        alias.normalized_queue_name = alias.normalized_queue_name or _normalize_alias_name(alias.queue_name)
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
            "moved_policies": moved_policies,
            "moved_aliases": moved_aliases,
            "merged_aliases": merged_aliases,
            "moved_alias_policies": moved_alias_policies,
        },
    )
    db.delete(source)
    db.commit()
    db.refresh(target)
    _annotate_identity_conflicts(db, actor.organization_id, [target])
    return target
