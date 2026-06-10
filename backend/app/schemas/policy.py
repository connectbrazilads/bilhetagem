from datetime import datetime, time

from pydantic import BaseModel, Field, model_validator

from app.models.print_policy import PolicyAction, PolicyRuleType
from app.schemas.job import PrintJobCreate


WEEKDAY_ALIASES = {
    "mon": 0,
    "seg": 0,
    "tue": 1,
    "ter": 1,
    "wed": 2,
    "qua": 2,
    "thu": 3,
    "qui": 3,
    "fri": 4,
    "sex": 4,
    "sat": 5,
    "sab": 5,
    "sun": 6,
    "dom": 6,
}


def validate_days_of_week(value: str | None) -> None:
    if value is None or value.strip() == "":
        return
    tokens = [token.strip().lower() for token in value.split(",") if token.strip()]
    invalid_tokens: list[str] = []
    for token in tokens:
        if token.isdigit():
            weekday = int(token)
            if weekday < 0 or weekday > 6:
                invalid_tokens.append(token)
            continue
        if token[:3] not in WEEKDAY_ALIASES:
            invalid_tokens.append(token)
    if invalid_tokens:
        raise ValueError(f"days_of_week contem valor invalido: {', '.join(invalid_tokens)}")


class PrintPolicyBase(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=255)
    priority: int = Field(default=100, ge=1, le=10000)
    is_active: bool = True
    rule_type: PolicyRuleType
    action: PolicyAction
    user_id: int | None = None
    department_id: int | None = None
    printer_id: int | None = None
    printer_alias_id: int | None = None
    queue_name: str | None = Field(default=None, max_length=180)
    max_pages: int | None = Field(default=None, ge=1, le=10000)
    days_of_week: str | None = Field(default=None, max_length=40)
    start_time: time | None = None
    end_time: time | None = None
    message: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_rule_fields(self):
        if self.rule_type == PolicyRuleType.max_pages and self.max_pages is None:
            raise ValueError("max_pages obrigatorio para regra de paginas")
        if self.rule_type == PolicyRuleType.time_window and (self.start_time is None or self.end_time is None):
            raise ValueError("start_time e end_time obrigatorios para regra por horario")
        validate_days_of_week(self.days_of_week)
        return self


class PrintPolicyCreate(PrintPolicyBase):
    pass


class PrintPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=255)
    priority: int | None = Field(default=None, ge=1, le=10000)
    is_active: bool | None = None
    rule_type: PolicyRuleType | None = None
    action: PolicyAction | None = None
    user_id: int | None = None
    department_id: int | None = None
    printer_id: int | None = None
    printer_alias_id: int | None = None
    queue_name: str | None = Field(default=None, max_length=180)
    max_pages: int | None = Field(default=None, ge=1, le=10000)
    days_of_week: str | None = Field(default=None, max_length=40)
    start_time: time | None = None
    end_time: time | None = None
    message: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_days(self):
        validate_days_of_week(self.days_of_week)
        return self


class PrintPolicyRead(PrintPolicyBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PrintPolicyReorder(BaseModel):
    policy_ids: list[int] = Field(min_length=1)


class PrintPolicySimulationRequest(PrintJobCreate):
    pass


class PrintPolicySimulationRead(BaseModel):
    matched: bool
    policy_id: int | None = None
    policy_name: str | None = None
    action: PolicyAction | None = None
    reason: str | None = None
    force_mono: bool = False
    effective_is_color: bool
    user_id: int
    printer_id: int
    printer_alias_id: int | None = None
