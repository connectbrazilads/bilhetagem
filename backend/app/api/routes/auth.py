from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    query = (
        db.query(User)
        .join(Organization)
        .filter(
            User.username == payload.username,
            User.is_active.is_(True),
            Organization.is_active.is_(True),
        )
    )
    if payload.organization_slug:
        query = query.filter(Organization.slug == payload.organization_slug)
        user = query.first()
    else:
        candidates = query.limit(2).all()
        if len(candidates) > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe a empresa para acessar")
        user = candidates[0] if candidates else None
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario ou senha invalidos")
    if user.role == UserRole.agent and not payload.organization_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe a empresa para autenticar o agent")
    token = create_access_token(user.username, {"role": user.role.value, "organization_id": user.organization_id})
    return TokenResponse(
        access_token=token,
        organization_id=user.organization_id,
        organization_slug=user.organization.slug if user.organization else None,
        organization_name=user.organization.name if user.organization else None,
    )
