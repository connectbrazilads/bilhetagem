from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def organization_allows_access(organization: Organization | None) -> bool:
    return bool(organization and organization.is_active and organization.billing_status != "suspended")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Annotated[Session, Depends(get_db)]) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        organization_id = payload.get("organization_id")
        if username is None or organization_id is None:
            raise credentials_exception
        organization_id = int(organization_id)
    except (JWTError, TypeError, ValueError) as exc:
        raise credentials_exception from exc

    user = (
        db.query(User)
        .filter(
            User.username == username,
            User.organization_id == organization_id,
            User.is_active.is_(True),
        )
        .first()
    )
    if user is None or not organization_allows_access(user.organization):
        raise credentials_exception
    return user


def get_current_organization(current_user: Annotated[User, Depends(get_current_user)]) -> Organization:
    return current_user.organization


def require_roles(*roles: UserRole):
    def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissao insuficiente")
        return current_user

    return dependency
