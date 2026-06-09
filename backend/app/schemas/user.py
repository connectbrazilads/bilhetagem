from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    full_name: str = Field(min_length=2, max_length=180)
    password: str | None = Field(default=None, min_length=8)
    role: UserRole = UserRole.user
    department_name: str | None = None
    monthly_limit: int = Field(default=500, ge=0)
    monthly_balance: float = Field(default=50.0, ge=0.0)


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    role: UserRole
    department_name: str | None = None
    is_active: bool
    created_at: datetime
    monthly_limit: int | None = None
    monthly_balance: float | None = None
    used_balance: float | None = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=180)
    role: UserRole | None = None
    department_name: str | None = None
    is_active: bool | None = None
    monthly_limit: int | None = Field(default=None, ge=0)
    monthly_balance: float | None = Field(default=None, ge=0.0)
