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
from app.schemas.policy import PrintPolicyCreate, PrintPolicyRead, PrintPolicyUpdate
from app.services.audit_service import write_audit

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
        write_audit(db, action="policy_created", entity="print_policies", entity_id=policy.id, actor_user_id=actor.id)
        db.commit()
        db.refresh(policy)
        return policy
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Politica ja cadastrada") from exc


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
    for field, value in data.items():
        if field in {"name", "description", "queue_name", "days_of_week", "message"}:
            setattr(policy, field, _clean_optional(value))
        else:
            setattr(policy, field, value)
    _validate_policy_fields(policy)
    try:
        write_audit(db, action="policy_updated", entity="print_policies", entity_id=policy.id, actor_user_id=actor.id)
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
    write_audit(db, action="policy_deleted", entity="print_policies", entity_id=policy.id, actor_user_id=actor.id)
    db.delete(policy)
    db.commit()
    return {"status": "deleted"}
