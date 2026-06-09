from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PrinterAlias(Base):
    __tablename__ = "printer_aliases"
    __table_args__ = (
        UniqueConstraint("agent_id", "queue_name", name="uq_printer_alias_agent_queue"),
        Index("ix_printer_aliases_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("print_agents.id"), nullable=True)
    queue_name: Mapped[str] = mapped_column(String(180), nullable=False)
    normalized_queue_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    computer_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    port_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    printer = relationship("Printer", back_populates="aliases")
    agent = relationship("PrintAgent", back_populates="aliases")
