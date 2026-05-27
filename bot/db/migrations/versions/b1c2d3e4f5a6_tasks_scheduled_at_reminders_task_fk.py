"""tasks: add scheduled_at; reminders: add task_id FK

Revision ID: b1c2d3e4f5a6
Revises: a3f2b1c4d5e6
Create Date: 2026-05-27 14:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a3f2b1c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scheduled_at to tasks
    op.add_column(
        "tasks",
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
    )
    # Add task_id to reminders
    op.add_column(
        "reminders",
        sa.Column("task_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_reminders_task_id",
        "reminders",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_reminders_task_id", "reminders", type_="foreignkey")
    op.drop_column("reminders", "task_id")
    op.drop_column("tasks", "scheduled_at")
