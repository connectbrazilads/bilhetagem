from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.agent_queue_action import AgentQueueActionStatus, AgentQueueActionType


class AgentVersionRead(BaseModel):
    latest_version: str
    update_available: bool
    mandatory: bool = False
    download_url: str | None = None
    sha256: str | None = None


class AgentReleaseFileRead(BaseModel):
    kind: str
    filename: str
    size_bytes: int
    sha256: str
    signature_status: str | None = None
    signer_subject: str | None = None
    download_url: str


class AgentReleaseRead(BaseModel):
    version: str
    channel: str = "stable"
    published_at: str | None = None
    notes: str | None = None
    checksums_url: str | None = None
    signature_status: str = "empty"
    signature_summary: str = "Nenhum arquivo publicado"
    files: list[AgentReleaseFileRead] = Field(default_factory=list)


class AgentDeploymentOrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool

    model_config = {"from_attributes": True}


class AgentQueuePayload(BaseModel):
    queue_name: str = Field(min_length=1, max_length=180)
    driver_name: str | None = Field(default=None, max_length=180)
    port_name: str | None = Field(default=None, max_length=180)
    connection_type: str | None = Field(default=None, max_length=40)
    ip_address: str | None = Field(default=None, max_length=45)
    serial_number: str | None = Field(default=None, max_length=80)
    device_id: str | None = Field(default=None, max_length=255)
    fingerprint: str | None = Field(default=None, max_length=255)

    @field_validator("queue_name")
    @classmethod
    def queue_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nome da fila obrigatorio")
        return value


class AgentLogPayload(BaseModel):
    level: str = Field(default="info", max_length=20)
    message: str = Field(min_length=1, max_length=1000)
    source: str | None = Field(default=None, max_length=80)
    occurred_at: datetime | None = None


class AgentHeartbeatPayload(BaseModel):
    agent_uid: str = Field(min_length=1, max_length=120)
    computer_name: str | None = Field(default=None, max_length=180)
    os_user: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=40)
    capture_mode: str | None = Field(default=None, max_length=40)
    event_log_enabled: bool | None = None
    auto_update_enabled: bool | None = None
    last_error: str | None = Field(default=None, max_length=500)
    queues: list[AgentQueuePayload] = Field(default_factory=list, max_length=200)
    logs: list[AgentLogPayload] = Field(default_factory=list, max_length=50)


class AgentQueueRead(BaseModel):
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
    is_present: bool = True

    model_config = {"from_attributes": True}


class AgentRecentJobRead(BaseModel):
    id: int
    username: str
    printer_name: str
    document_name: str | None
    pages: int
    is_color: bool
    status: str
    policy_name: str | None = None
    policy_action: str | None = None
    submitted_at: datetime


class AgentHealthAlertRead(BaseModel):
    code: str
    severity: str
    message: str


class AgentLogRead(BaseModel):
    id: int
    level: str
    message: str
    source: str | None
    occurred_at: datetime
    received_at: datetime

    model_config = {"from_attributes": True}


class AgentQueueActionCreate(BaseModel):
    action_type: AgentQueueActionType
    queue_name: str = Field(min_length=1, max_length=180)
    printer_id: int | None = None
    driver_name: str | None = Field(default=None, max_length=180)
    port_name: str | None = Field(default=None, max_length=180)
    ip_address: str | None = Field(default=None, max_length=45)

    @field_validator("queue_name")
    @classmethod
    def queue_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nome da fila obrigatorio")
        return value


class AgentQueueBulkActionCreate(AgentQueueActionCreate):
    agent_ids: list[int] = Field(default_factory=list, max_length=500)
    apply_to_all: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        if not self.apply_to_all and not self.agent_ids:
            raise ValueError("Informe agent_ids ou marque apply_to_all")
        return self


class AgentQueueActionResult(BaseModel):
    status: AgentQueueActionStatus
    result_message: str | None = Field(default=None, max_length=500)
    agent_uid: str | None = Field(default=None, min_length=1, max_length=120)


class AgentQueueActionRead(BaseModel):
    id: int
    agent_id: int
    printer_id: int | None
    requested_by_user_id: int | None
    action_type: AgentQueueActionType
    queue_name: str
    driver_name: str | None
    port_name: str | None
    ip_address: str | None
    status: AgentQueueActionStatus
    result_message: str | None
    requested_at: datetime
    dispatched_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PrintAgentRead(BaseModel):
    id: int
    agent_uid: str
    computer_name: str | None
    os_user: str | None
    version: str | None
    ip_address: str | None
    capture_mode: str | None
    event_log_enabled: bool | None
    auto_update_enabled: bool | None
    last_error: str | None
    last_seen_at: datetime | None
    created_at: datetime
    is_online: bool
    status: str
    health_alerts: list[AgentHealthAlertRead] = Field(default_factory=list)
    aliases: list[AgentQueueRead] = Field(default_factory=list)
    recent_jobs: list[AgentRecentJobRead] = Field(default_factory=list)
    queue_actions: list[AgentQueueActionRead] = Field(default_factory=list)
    recent_logs: list[AgentLogRead] = Field(default_factory=list)
