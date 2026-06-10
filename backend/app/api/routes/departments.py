from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.department import Department
from app.models.print_policy import PrintPolicy
from app.models.user import User, UserRole
from app.schemas.department import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentRead])
def list_departments(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[Department]:
    return (
        db.query(Department)
        .filter(Department.organization_id == actor.organization_id)
        .order_by(Department.name)
        .all()
    )


@router.post("", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Department:
    department = Department(organization_id=actor.organization_id, name=payload.name.strip())
    db.add(department)
    try:
        db.flush()
        write_audit(db, action="department_created", entity="departments", entity_id=department.id, actor_user_id=actor.id)
        db.commit()
        db.refresh(department)
        return department
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Departamento ja cadastrado") from exc


@router.put("/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Department:
    department = db.query(Department).filter(Department.organization_id == actor.organization_id, Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Departamento nao encontrado")
    department.name = payload.name.strip()
    try:
        write_audit(db, action="department_updated", entity="departments", entity_id=department.id, actor_user_id=actor.id)
        db.commit()
        db.refresh(department)
        return department
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Departamento ja cadastrado") from exc


@router.delete("/{department_id}")
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict[str, str]:
    department = db.query(Department).filter(Department.organization_id == actor.organization_id, Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Departamento nao encontrado")
    users_count = db.query(User).filter(User.organization_id == actor.organization_id, User.department_id == department.id).count()
    policies_count = db.query(PrintPolicy).filter(PrintPolicy.organization_id == actor.organization_id, PrintPolicy.department_id == department.id).count()
    if users_count or policies_count:
        raise HTTPException(status_code=400, detail="Departamento em uso por usuarios ou politicas")
    write_audit(db, action="department_deleted", entity="departments", entity_id=department.id, actor_user_id=actor.id)
    db.delete(department)
    db.commit()
    return {"status": "deleted"}
