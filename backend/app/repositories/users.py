from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.department import Department
from app.models.user import User
from app.schemas.user import UserCreate


def get_or_create_department(db: Session, name: str | None, organization_id: int) -> Department | None:
    if not name:
        return None
    department = db.query(Department).filter(Department.organization_id == organization_id, Department.name == name).first()
    if department:
        return department
    department = Department(organization_id=organization_id, name=name)
    db.add(department)
    db.flush()
    return department


def resolve_department(db: Session, organization_id: int, department_id: int | None, department_name: str | None) -> Department | None:
    if department_id is not None:
        return db.query(Department).filter(Department.organization_id == organization_id, Department.id == department_id).first()
    return get_or_create_department(db, department_name, organization_id)


def create_user(db: Session, payload: UserCreate, organization_id: int) -> User:
    department = resolve_department(db, organization_id, payload.department_id, payload.department_name)
    if payload.department_id is not None and department is None:
        raise ValueError("Departamento nao encontrado")
    existing = (
        db.query(User)
        .filter(User.organization_id == organization_id, func.lower(User.username) == payload.username.lower())
        .first()
    )
    if existing:
        raise ValueError("Usuario ja cadastrado")
    user = User(
        organization_id=organization_id,
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password) if payload.password else None,
        role=payload.role,
        department=department,
    )
    db.add(user)
    db.flush()
    return user
