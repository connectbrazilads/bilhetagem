from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.password_policy import is_unsafe_initial_password
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.services.organization_service import get_or_create_default_organization


def validate_seed_password(password: str, setting_name: str) -> None:
    if is_unsafe_initial_password(password):
        raise RuntimeError(f"{setting_name} deve ser definido com uma senha propria antes de criar usuarios iniciais.")


def ensure_user(db: Session, *, username: str, password: str, role: UserRole, full_name: str) -> None:
    organization = get_or_create_default_organization(db)
    user = db.query(User).filter(User.organization_id == organization.id, User.username == username).first()
    if user:
        return
    validate_seed_password(password, f"Senha inicial de {username}")
    db.add(
        User(
            organization_id=organization.id,
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
    )


def main() -> None:
    db = SessionLocal()
    try:
        ensure_user(
            db,
            username=settings.initial_admin_username,
            password=settings.initial_admin_password,
            role=UserRole.admin,
            full_name="Administrador",
        )
        ensure_user(
            db,
            username=settings.initial_agent_username,
            password=settings.initial_agent_password,
            role=UserRole.agent,
            full_name="Agente Windows",
        )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
