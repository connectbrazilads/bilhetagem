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
        if username is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    query = db.query(User).filter(User.username == username, User.is_active.is_(True))
    if organization_id is not None:
        query = query.filter(User.organization_id == int(organization_id))
    user = query.first()
    if user is None or not user.organization or not user.organization.is_active:
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
