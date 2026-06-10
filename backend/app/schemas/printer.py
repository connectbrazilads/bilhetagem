from datetime import datetime

from pydantic import BaseModel, Field


class PrinterCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    location: str | None = Field(default=None, max_length=180)
    is_color: bool = False
    cost_mono: float | None = Field(default=None, ge=0)
    cost_color: float | None = Field(default=None, ge=0)
    ip_address: str | None = Field(default=None, max_length=45)


class PrinterAliasRead(BaseModel):
    id: int
    printer_id: int | None
    queue_name: str
    computer_name: str | None
    driver_name: str | None
    port_name: str | None
    connection_type: str | None
    ip_address: str | None
    serial_number: str | None
    device_id: str | None
    fingerprint: str | None
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}


class PrinterAliasBind(BaseModel):
    printer_id: int | None = None


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
    aliases: list[PrinterAliasRead] = Field(default_factory=list)

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
    agent_uid: str | None = Field(default=None, min_length=1, max_length=120)
    toner_level: int | None = Field(default=None, ge=0, le=100)
    toner_levels: dict[str, int] | None = None
    paper_status: str | None = Field(default=None, max_length=50)
    serial_number: str | None = Field(default=None, max_length=80)
    page_counter: int | None = Field(default=None, ge=0)
