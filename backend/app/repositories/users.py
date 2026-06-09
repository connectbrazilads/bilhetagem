from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.department import Department
from app.models.user import User
from app.schemas.user import UserCreate


def get_or_create_department(db: Session, name: str | None) -> Department | None:
    if not name:
        return None
    department = db.query(Department).filter(Department.name == name).first()
    if department:
        return department
    department = Department(name=name)
    db.add(department)
    db.flush()
    return department


def create_user(db: Session, payload: UserCreate) -> User:
    department = get_or_create_department(db, payload.department_name)
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password) if payload.password else None,
        role=payload.role,
        department=department,
    )
    db.add(user)
    db.flush()
    return user
