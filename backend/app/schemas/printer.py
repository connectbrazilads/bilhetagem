from datetime import datetime

from pydantic import BaseModel, Field


class PrinterCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    location: str | None = Field(default=None, max_length=180)
    is_color: bool = False
    cost_mono: float = 0.05
    cost_color: float = 0.25
    ip_address: str | None = Field(default=None, max_length=45)


class PrinterRead(BaseModel):
    id: int
    name: str
    location: str | None
    is_color: bool
    cost_mono: float
    cost_color: float
    is_active: bool
    ip_address: str | None
    toner_level: int | None
    toner_levels: dict[str, int] | None
    paper_status: str | None
    serial_number: str | None
    page_counter: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PrinterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    location: str | None = Field(default=None, max_length=180)
    is_color: bool | None = None
    cost_mono: float | None = None
    cost_color: float | None = None
    is_active: bool | None = None
    ip_address: str | None = Field(default=None, max_length=45)


class PrinterStatusUpdate(BaseModel):
    toner_level: int | None = Field(default=None, ge=0, le=100)
    toner_levels: dict[str, int] | None = None
    paper_status: str | None = Field(default=None, max_length=50)
    serial_number: str | None = Field(default=None, max_length=80)
    page_counter: int | None = Field(default=None, ge=0)
