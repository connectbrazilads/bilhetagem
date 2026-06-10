from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
    organization_slug: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str | None = None
    organization_id: int | None = None
    organization_slug: str | None = None
    organization_name: str | None = None


class AuthContextResponse(BaseModel):
    username: str
    full_name: str
    role: str
    organization_id: int
    organization_slug: str
    organization_name: str
