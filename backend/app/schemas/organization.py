from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.password_policy import is_unsafe_initial_password


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    is_active: bool = True
    billing_plan: Literal["starter", "professional", "enterprise"] = "starter"
    billing_status: Literal["trial", "active", "past_due", "suspended"] = "trial"
    contracted_printer_limit: int = Field(default=0, ge=0, le=100_000)
    admin_username: str = Field(default="admin", min_length=2, max_length=120)
    admin_password: str = Field(min_length=8, max_length=120)
    agent_username: str = Field(default="agent", min_length=2, max_length=120)
    agent_password: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def validate_initial_users(self):
        if self.admin_username.strip().lower() == self.agent_username.strip().lower():
            raise ValueError("Admin inicial e usuario do agent devem ser diferentes")
        if is_unsafe_initial_password(self.admin_password):
            raise ValueError("Senha inicial do admin deve ser propria e nao pode usar valor padrao")
        if is_unsafe_initial_password(self.agent_password):
            raise ValueError("Senha inicial do agent deve ser propria e nao pode usar valor padrao")
        if self.admin_password.strip() == self.agent_password.strip():
            raise ValueError("Senhas iniciais do admin e do agent devem ser diferentes")
        return self


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    is_active: bool | None = None
    billing_plan: Literal["starter", "professional", "enterprise"] | None = None
    billing_status: Literal["trial", "active", "past_due", "suspended"] | None = None
    contracted_printer_limit: int | None = Field(default=None, ge=0, le=100_000)


class OrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    billing_plan: str = "starter"
    billing_status: str = "trial"
    contracted_printer_limit: int = 0
    created_at: datetime
    users_count: int = 0
    printers_count: int = 0
    agents_count: int = 0
    online_agents_count: int = 0
    offline_agents_count: int = 0
    jobs_count: int = 0
    jobs_month: int = 0
    pages_month: int = 0
    cost_month: float = 0.0

    model_config = {"from_attributes": True}
