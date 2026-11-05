
"""add processed events

Revision ID: 18013a21a9a4
Revises: ac7f05df60b7
Create Date: 2026-11-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "18013a21a9a4"
down_revision: Union[str, Sequence[str], None] = "ac7f05df60b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create processed events table."""

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    """Drop processed events table."""

    op.drop_table("processed_events")
