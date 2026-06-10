"""add remote queue actions

Revision ID: 0011_agent_queue_actions
Revises: 0010_agent_health
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_agent_queue_actions"
down_revision: Union[str, None] = "0010_agent_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_enum_if_missing(enum_name: str, values: Sequence[str]) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
        CREATE TYPE {enum_name} AS ENUM ({quoted_values});
    END IF;
END
$$;
"""
    )


def _existing_enum(enum_name: str, values: Sequence[str]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=enum_name, create_type=False, _create_events=False)


def upgrade() -> None:
    action_type_values = ("create_queue", "remove_queue")
    action_status_values = ("pending", "running", "succeeded", "failed")
    _create_enum_if_missing("agentqueueactiontype", action_type_values)
    _create_enum_if_missing("agentqueueactionstatus", action_status_values)
    action_type = _existing_enum("agentqueueactiontype", action_type_values)
    action_status = _existing_enum("agentqueueactionstatus", action_status_values)

    op.create_table(
        "agent_queue_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("printer_id", sa.Integer(), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("action_type", action_type, nullable=False),
        sa.Column("queue_name", sa.String(length=180), nullable=False),
        sa.Column("driver_name", sa.String(length=180), nullable=True),
        sa.Column("port_name", sa.String(length=180), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("status", action_status, nullable=False),
        sa.Column("result_message", sa.String(length=500), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["print_agents.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["printer_id"], ["printers.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_queue_actions_agent_status", "agent_queue_actions", ["agent_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_agent_queue_actions_agent_status", table_name="agent_queue_actions")
    op.drop_table("agent_queue_actions")
    sa.Enum(name="agentqueueactionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="agentqueueactiontype").drop(op.get_bind(), checkfirst=True)
