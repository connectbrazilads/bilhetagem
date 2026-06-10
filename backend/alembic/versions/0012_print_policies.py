"""add print policies

Revision ID: 0012_print_policies
Revises: 0011_agent_queue_actions
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_print_policies"
down_revision: Union[str, None] = "0011_agent_queue_actions"
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
    rule_type_values = ("always", "max_pages", "color", "time_window")
    action_values = ("allow", "block", "require_release", "force_mono")
    _create_enum_if_missing("policyruletype", rule_type_values)
    _create_enum_if_missing("policyaction", action_values)
    rule_type = _existing_enum("policyruletype", rule_type_values)
    action = _existing_enum("policyaction", action_values)

    op.create_table(
        "print_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("rule_type", rule_type, nullable=False),
        sa.Column("action", action, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("printer_id", sa.Integer(), nullable=True),
        sa.Column("printer_alias_id", sa.Integer(), nullable=True),
        sa.Column("queue_name", sa.String(length=180), nullable=True),
        sa.Column("max_pages", sa.Integer(), nullable=True),
        sa.Column("days_of_week", sa.String(length=40), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["printer_alias_id"], ["printer_aliases.id"]),
        sa.ForeignKeyConstraint(["printer_id"], ["printers.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_print_policies_org_name"),
    )
    op.create_index("ix_print_policies_org_active_priority", "print_policies", ["organization_id", "is_active", "priority"])
    op.add_column("print_jobs", sa.Column("policy_id", sa.Integer(), nullable=True))
    op.add_column("print_jobs", sa.Column("policy_name", sa.String(length=180), nullable=True))
    op.add_column("print_jobs", sa.Column("policy_action", sa.String(length=40), nullable=True))
    op.create_foreign_key("fk_print_jobs_policy_id", "print_jobs", "print_policies", ["policy_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_print_jobs_policy_id", "print_jobs", type_="foreignkey")
    op.drop_column("print_jobs", "policy_action")
    op.drop_column("print_jobs", "policy_name")
    op.drop_column("print_jobs", "policy_id")
    op.drop_index("ix_print_policies_org_active_priority", table_name="print_policies")
    op.drop_table("print_policies")
    sa.Enum(name="policyaction").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="policyruletype").drop(op.get_bind(), checkfirst=True)
