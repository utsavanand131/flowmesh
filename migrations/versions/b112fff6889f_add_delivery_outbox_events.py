"""add delivery outbox events

Revision ID: b112fff6889f
Revises: 54c37e4c7b51
Create Date: 2026-09-16 17:31:10.215440

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b112fff6889f"
down_revision: Union[str, Sequence[str], None] = "54c37e4c7b51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create delivery outbox events table."""

    op.create_table(
        "delivery_outbox_events",
        sa.Column(
            "event_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "aggregate_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "payload",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "published",
            sa.Boolean(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    """Drop delivery outbox events table."""

    op.drop_table("delivery_outbox_events")