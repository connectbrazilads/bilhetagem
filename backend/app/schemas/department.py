from datetime import datetime

from pydantic import BaseModel
from pydantic import Field


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class DepartmentRead(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}
