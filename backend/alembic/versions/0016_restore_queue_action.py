"""add restore queue action

Revision ID: 0016_restore_queue_action
Revises: 0015_agent_user_role
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0016_restore_queue_action"
down_revision: Union[str, None] = "0015_agent_user_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        context = op.get_context()
        with context.autocommit_block():
            op.execute("ALTER TYPE agentqueueactiontype ADD VALUE IF NOT EXISTS 'restore_queue'")


def downgrade() -> None:
    pass
