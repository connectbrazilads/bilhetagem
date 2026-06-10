from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.department import Department
from app.models.print_policy import PrintPolicy, PolicyRuleType
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User, UserRole
from app.schemas.policy import (
    PrintPolicyCreate,
    PrintPolicyRead,
    PrintPolicyReorder,
    PrintPolicySimulationRead,
    PrintPolicySimulationRequest,
    PrintPolicyUpdate,
)
from app.services.audit_service import write_audit
from app.services.policy_service import simulate_print_policy

router = APIRouter(prefix="/policies", tags=["policies"])


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validate_scope(db: Session, payload: PrintPolicyCreate | PrintPolicyUpdate, organization_id: int) -> None:
    if getattr(payload, "user_id", None) is not None:
        if not db.query(User).filter(User.organization_id == organization_id, User.id == payload.user_id).first():
            raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if getattr(payload, "department_id", None) is not None:
        if not db.query(Department).filter(Department.organization_id == organization_id, Department.id == payload.department_id).first():
            raise HTTPException(status_code=404, detail="Departamento nao encontrado")
    if getattr(payload, "printer_id", None) is not None:
        if not db.query(Printer).filter(Printer.organization_id == organization_id, Printer.id == payload.printer_id).first():
            raise HTTPException(status_code=404, detail="Impressora nao encontrada")
    if getattr(payload, "printer_alias_id", None) is not None:
        if not db.query(PrinterAlias).filter(PrinterAlias.organization_id == organization_id, PrinterAlias.id == payload.printer_alias_id).first():
            raise HTTPException(status_code=404, detail="Fila/alias nao encontrada")


def _validate_policy_fields(policy: PrintPolicy) -> None:
    if policy.rule_type == PolicyRuleType.max_pages and policy.max_pages is None:
        raise HTTPException(status_code=422, detail="max_pages obrigatorio para regra de paginas")
    if policy.rule_type == PolicyRuleType.time_window and (policy.start_time is None or policy.end_time is None):
        raise HTTPException(status_code=422, detail="start_time e end_time obrigatorios para regra por horario")


def _policy_snapshot(policy: PrintPolicy) -> dict:
    return {
        "name": policy.name,
        "description": policy.description,
        "priority": policy.priority,
        "is_active": policy.is_active,
        "rule_type": policy.rule_type.value,
        "action": policy.action.value,
        "user_id": policy.user_id,
        "department_id": policy.department_id,
        "printer_id": policy.printer_id,
        "printer_alias_id": policy.printer_alias_id,
        "queue_name": policy.queue_name,
        "max_pages": policy.max_pages,
        "days_of_week": policy.days_of_week,
        "start_time": policy.start_time.isoformat() if policy.start_time else None,
        "end_time": policy.end_time.isoformat() if policy.end_time else None,
        "message": policy.message,
    }


def _changed_values(before: dict, after: dict) -> dict:
    return {
        key: {"before": before.get(key), "after": after_value}
        for key, after_value in after.items()
        if before.get(key) != after_value
    }


@router.get("", response_model=list[PrintPolicyRead])
def list_policies(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[PrintPolicy]:
    return (
        db.query(PrintPolicy)
        .filter(PrintPolicy.organization_id == actor.organization_id)
        .order_by(PrintPolicy.priority, PrintPolicy.id)
        .all()
    )


@router.post("", response_model=PrintPolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PrintPolicyCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> PrintPolicy:
    _validate_scope(db, payload, actor.organization_id)
    policy = PrintPolicy(
        organization_id=actor.organization_id,
        name=payload.name.strip(),
        description=_clean_optional(payload.description),
        priority=payload.priority,
        is_active=payload.is_active,
        rule_type=payload.rule_type,
        action=payload.action,
        user_id=payload.user_id,
        department_id=payload.department_id,
        printer_id=payload.printer_id,
        printer_alias_id=payload.printer_alias_id,
        queue_name=_clean_optional(payload.queue_name),
        max_pages=payload.max_pages,
        days_of_week=_clean_optional(payload.days_of_week),
        start_time=payload.start_time,
        end_time=payload.end_time,
        message=_clean_optional(payload.message),
    )
    _validate_policy_fields(policy)
    db.add(policy)
    try:
        db.flush()
        write_audit(
            db,
            action="policy_created",
            entity="print_policies",
            entity_id=policy.id,
            actor_user_id=actor.id,
            metadata={"snapshot": _policy_snapshot(policy)},
        )
        db.commit()
        db.refresh(policy)
        return policy
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Politica ja cadastrada") from exc


@router.post("/simulate", response_model=PrintPolicySimulationRead)
def simulate_policy(
    payload: PrintPolicySimulationRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> PrintPolicySimulationRead:
    try:
        simulation = simulate_print_policy(db, payload, actor.organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    decision = simulation.decision
    return PrintPolicySimulationRead(
        matched=decision.policy is not None,
        policy_id=decision.policy.id if decision.policy else None,
        policy_name=decision.policy.name if decision.policy else None,
        action=decision.action,
        reason=decision.reason,
        force_mono=decision.force_mono,
        effective_is_color=payload.is_color and not decision.force_mono,
        user_id=simulation.user.id,
        printer_id=simulation.printer.id,
        printer_alias_id=simulation.alias.id if simulation.alias else None,
    )


@router.post("/reorder", response_model=list[PrintPolicyRead])
def reorder_policies(
    payload: PrintPolicyReorder,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> list[PrintPolicy]:
    current_policies = (
        db.query(PrintPolicy)
        .filter(PrintPolicy.organization_id == actor.organization_id)
        .order_by(PrintPolicy.priority, PrintPolicy.id)
        .all()
    )
    current_ids = [policy.id for policy in current_policies]
    requested_ids = payload.policy_ids
    if len(set(requested_ids)) != len(requested_ids):
        raise HTTPException(status_code=422, detail="Lista de politicas contem IDs duplicados")
    if set(requested_ids) != set(current_ids):
        raise HTTPException(status_code=422, detail="Informe todas as politicas da empresa para reordenar")

    by_id = {policy.id: policy for policy in current_policies}
    old_order = [{"id": policy.id, "priority": policy.priority} for policy in current_policies]
    for index, policy_id in enumerate(requested_ids, start=1):
        by_id[policy_id].priority = index * 10

    write_audit(
        db,
        action="policy_reordered",
        entity="print_policies",
        actor_user_id=actor.id,
        metadata={
            "old_order": old_order,
            "new_order": [{"id": policy_id, "priority": index * 10} for index, policy_id in enumerate(requested_ids, start=1)],
        },
    )
    db.commit()
    return (
        db.query(PrintPolicy)
        .filter(PrintPolicy.organization_id == actor.organization_id)
        .order_by(PrintPolicy.priority, PrintPolicy.id)
        .all()
    )


@router.put("/{policy_id}", response_model=PrintPolicyRead)
def update_policy(
    policy_id: int,
    payload: PrintPolicyUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> PrintPolicy:
    policy = db.query(PrintPolicy).filter(PrintPolicy.organization_id == actor.organization_id, PrintPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Politica nao encontrada")
    _validate_scope(db, payload, actor.organization_id)

    data = payload.model_dump(exclude_unset=True)
    before = _policy_snapshot(policy)
    for field, value in data.items():
        if field in {"name", "description", "queue_name", "days_of_week", "message"}:
            setattr(policy, field, _clean_optional(value))
        else:
            setattr(policy, field, value)
    _validate_policy_fields(policy)
    try:
        changes = _changed_values(before, _policy_snapshot(policy))
        if changes:
            write_audit(
                db,
                action="policy_updated",
                entity="print_policies",
                entity_id=policy.id,
                actor_user_id=actor.id,
                metadata={"changes": changes},
            )
        db.commit()
        db.refresh(policy)
        return policy
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Politica ja cadastrada") from exc


@router.delete("/{policy_id}")
def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict[str, str]:
    policy = db.query(PrintPolicy).filter(PrintPolicy.organization_id == actor.organization_id, PrintPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Politica nao encontrada")
    write_audit(
        db,
        action="policy_deleted",
        entity="print_policies",
        entity_id=policy.id,
        actor_user_id=actor.id,
        metadata={"snapshot": _policy_snapshot(policy)},
    )
    db.delete(policy)
    db.commit()
    return {"status": "deleted"}
