"""add agent and printer aliases

Revision ID: 0007_add_agent_and_printer_aliases
Revises: 0006_add_toner_levels
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_agent_and_printer_aliases"
down_revision: Union[str, None] = "0006_add_toner_levels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "print_agents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_uid", sa.String(length=120), nullable=False),
        sa.Column("computer_name", sa.String(length=180), nullable=True),
        sa.Column("os_user", sa.String(length=120), nullable=True),
        sa.Column("version", sa.String(length=40), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_uid"),
    )
    op.create_table(
        "printer_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("printer_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("queue_name", sa.String(length=180), nullable=False),
        sa.Column("normalized_queue_name", sa.String(length=180), nullable=True),
        sa.Column("computer_name", sa.String(length=180), nullable=True),
        sa.Column("driver_name", sa.String(length=180), nullable=True),
        sa.Column("port_name", sa.String(length=180), nullable=True),
        sa.Column("connection_type", sa.String(length=40), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("serial_number", sa.String(length=80), nullable=True),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("fingerprint", sa.String(length=255), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["print_agents.id"]),
        sa.ForeignKeyConstraint(["printer_id"], ["printers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "queue_name", name="uq_printer_alias_agent_queue"),
    )
    op.create_index("ix_printer_aliases_fingerprint", "printer_aliases", ["fingerprint"])
    op.add_column("print_jobs", sa.Column("printer_alias_id", sa.Integer(), nullable=True))
    op.add_column("print_jobs", sa.Column("agent_id", sa.Integer(), nullable=True))
    op.add_column("print_jobs", sa.Column("computer_name", sa.String(length=180), nullable=True))
    op.add_column("print_jobs", sa.Column("queue_name", sa.String(length=180), nullable=True))
    op.create_foreign_key("fk_print_jobs_printer_alias_id", "print_jobs", "printer_aliases", ["printer_alias_id"], ["id"])
    op.create_foreign_key("fk_print_jobs_agent_id", "print_jobs", "print_agents", ["agent_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_print_jobs_agent_id", "print_jobs", type_="foreignkey")
    op.drop_constraint("fk_print_jobs_printer_alias_id", "print_jobs", type_="foreignkey")
    op.drop_column("print_jobs", "queue_name")
    op.drop_column("print_jobs", "computer_name")
    op.drop_column("print_jobs", "agent_id")
    op.drop_column("print_jobs", "printer_alias_id")
    op.drop_index("ix_printer_aliases_fingerprint", table_name="printer_aliases")
    op.drop_table("printer_aliases")
    op.drop_table("print_agents")
