from pydantic import BaseModel, Field


class QuotaRead(BaseModel):
    id: int
    user_id: int
    username: str
    year: int
    month: int
    monthly_limit: int
    used_pages: int
    remaining_pages: int


class QuotaUpdate(BaseModel):
    monthly_limit: int = Field(ge=0)
