from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditLogRead(BaseModel):
    id: int
    actor_user_id: int | None = None
    actor_username: str | None = None
    action: str
    entity: str
    entity_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditLogFacets(BaseModel):
    actions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
