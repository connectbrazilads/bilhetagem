from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.audit_log import AuditLog
from app.models.print_job import PrintJob
from app.models.quota import Quota
from app.models.user import User, UserRole
from app.repositories.users import create_user, get_or_create_department, resolve_department
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/users", tags=["users"])


def _read_user(user: User, db: Session) -> UserRead:
    from app.services.quota_service import get_or_create_current_quota
    quota = get_or_create_current_quota(db, user)
    return UserRead(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        department_id=user.department_id,
        department_name=user.department.name if user.department else None,
        is_active=user.is_active,
        created_at=user.created_at,
        monthly_limit=quota.monthly_limit if quota else None,
        monthly_balance=quota.monthly_balance if quota else None,
        used_balance=quota.used_balance if quota else None,
    )


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[UserRead]:
    users = db.query(User).filter(User.organization_id == _.organization_id).order_by(User.username).all()
    return [_read_user(user, db) for user in users]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    payload: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> UserRead:
    try:
        user = create_user(db, payload, actor.organization_id)
        now = datetime.now(timezone.utc)
        quota = Quota(
            user_id=user.id,
            organization_id=actor.organization_id,
            year=now.year,
            month=now.month,
            monthly_limit=payload.monthly_limit,
            used_pages=0,
            monthly_balance=payload.monthly_balance,
            used_balance=0.0,
        )
        db.add(quota)
        write_audit(db, action="user_created", entity="users", entity_id=user.id, actor_user_id=actor.id)
        db.commit()
        db.refresh(user)
        return _read_user(user, db)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Usuário já cadastrado") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{user_id}", response_model=UserRead)
def update_user_endpoint(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> UserRead:
    user = db.query(User).filter(User.organization_id == actor.organization_id, User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    fields_set = payload.model_fields_set
    if "department_id" in fields_set:
        department = resolve_department(db, actor.organization_id, payload.department_id, None)
        if payload.department_id is not None and department is None:
            raise HTTPException(status_code=404, detail="Departamento nao encontrado")
        user.department = department
    elif "department_name" in fields_set:
        user.department = get_or_create_department(db, payload.department_name, actor.organization_id)
    
    if payload.monthly_limit is not None or payload.monthly_balance is not None:
        from app.services.quota_service import get_or_create_current_quota
        quota = get_or_create_current_quota(db, user)
        if payload.monthly_limit is not None:
            quota.monthly_limit = payload.monthly_limit
        if payload.monthly_balance is not None:
            quota.monthly_balance = payload.monthly_balance
        
    write_audit(db, action="user_updated", entity="users", entity_id=user.id, actor_user_id=actor.id)
    db.commit()
    db.refresh(user)
    return _read_user(user, db)


@router.delete("/{user_id}")
def delete_user_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict[str, str | int]:
    user = db.query(User).filter(User.organization_id == actor.organization_id, User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="Nao e possivel excluir o usuario logado")
    if user.username.lower() in {"admin", "agent"} or user.role == UserRole.agent:
        raise HTTPException(status_code=400, detail="Usuario tecnico nao pode ser excluido")

    deleted_jobs = db.query(PrintJob).filter(PrintJob.organization_id == actor.organization_id, PrintJob.user_id == user.id).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.organization_id == actor.organization_id, AuditLog.actor_user_id == user.id).update(
        {AuditLog.actor_user_id: None},
        synchronize_session=False,
    )
    write_audit(
        db,
        action="user_deleted",
        entity="users",
        entity_id=user.id,
        actor_user_id=actor.id,
        metadata={"username": user.username, "deleted_jobs": deleted_jobs},
    )
    db.delete(user)
    db.commit()
    return {"status": "deleted", "deleted_jobs": deleted_jobs}
