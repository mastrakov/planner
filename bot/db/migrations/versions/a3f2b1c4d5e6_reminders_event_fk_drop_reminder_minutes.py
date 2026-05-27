"""reminders: add event_id FK, drop calendar_events.reminder_minutes

Revision ID: a3f2b1c4d5e6
Revises: 1a84aa9cb3d8
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f2b1c4d5e6"
down_revision: Union[str, Sequence[str], None] = "1a84aa9cb3d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add event_id column first (nullable, no FK yet)
    op.add_column(
        "reminders",
        sa.Column("event_id", sa.Integer(), nullable=True),
    )

    # 2. Migrate existing reminder_minutes → reminders rows
    #    (column now exists, safe to INSERT into it)
    op.execute(
        """
        INSERT INTO reminders (user_id, event_id, title, remind_at, repeat, is_sent, created_at)
        SELECT
            ce.user_id,
            ce.id,
            'Напоминание: ' || ce.title,
            ce.starts_at - (ce.reminder_minutes * INTERVAL '1 minute'),
            'NONE',
            FALSE,
            NOW()
        FROM calendar_events ce
        WHERE ce.reminder_minutes IS NOT NULL
          AND ce.starts_at - (ce.reminder_minutes * INTERVAL '1 minute') > NOW()
        """
    )

    # 3. Add FK constraint now that data is consistent
    op.create_foreign_key(
        "fk_reminders_event_id",
        "reminders",
        "calendar_events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 4. Drop reminder_minutes from calendar_events
    op.drop_column("calendar_events", "reminder_minutes")


def downgrade() -> None:
    # Restore reminder_minutes column (data loss for multi-reminder rows is accepted)
    op.add_column(
        "calendar_events",
        sa.Column("reminder_minutes", sa.Integer(), nullable=True),
    )

    # Back-fill: take the smallest offset among linked reminders
    op.execute(
        """
        UPDATE calendar_events ce
        SET reminder_minutes = (
            SELECT EXTRACT(EPOCH FROM (ce.starts_at - r.remind_at)) / 60
            FROM reminders r
            WHERE r.event_id = ce.id
              AND r.is_sent = FALSE
            ORDER BY r.remind_at ASC
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM reminders r WHERE r.event_id = ce.id AND r.is_sent = FALSE
        )
        """
    )

    # Drop FK and column added in upgrade
    op.drop_constraint("fk_reminders_event_id", "reminders", type_="foreignkey")
    op.drop_column("reminders", "event_id")
