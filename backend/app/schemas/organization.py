from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    is_active: bool = True
    admin_username: str = Field(default="admin", min_length=2, max_length=120)
    admin_password: str = Field(min_length=8, max_length=120)
    agent_username: str = Field(default="agent", min_length=2, max_length=120)
    agent_password: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def validate_initial_users(self):
        if self.admin_username.strip().lower() == self.agent_username.strip().lower():
            raise ValueError("Admin inicial e usuario do agent devem ser diferentes")
        return self


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    is_active: bool | None = None


class OrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    users_count: int = 0
    printers_count: int = 0
    agents_count: int = 0
    online_agents_count: int = 0
    offline_agents_count: int = 0
    jobs_count: int = 0
    pages_month: int = 0
    cost_month: float = 0.0

    model_config = {"from_attributes": True}
