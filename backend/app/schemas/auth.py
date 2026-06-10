from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
    organization_slug: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization_id: int | None = None
    organization_slug: str | None = None
    organization_name: str | None = None
