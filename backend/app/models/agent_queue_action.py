import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentQueueActionType(str, enum.Enum):
    create_queue = "create_queue"
    remove_queue = "remove_queue"
    restore_queue = "restore_queue"


class AgentQueueActionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AgentQueueAction(Base):
    __tablename__ = "agent_queue_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), default=1, nullable=False)
    agent_id: Mapped[int] = mapped_column(ForeignKey("print_agents.id"), nullable=False)
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action_type: Mapped[AgentQueueActionType] = mapped_column(Enum(AgentQueueActionType), nullable=False)
    queue_name: Mapped[str] = mapped_column(String(180), nullable=False)
    driver_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    port_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    status: Mapped[AgentQueueActionStatus] = mapped_column(
        Enum(AgentQueueActionStatus),
        default=AgentQueueActionStatus.pending,
        nullable=False,
    )
    result_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent = relationship("PrintAgent", back_populates="queue_actions")
    printer = relationship("Printer")
    requested_by = relationship("User")
