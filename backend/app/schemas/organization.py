from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    is_active: bool = True


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
    jobs_count: int = 0

    model_config = {"from_attributes": True}
