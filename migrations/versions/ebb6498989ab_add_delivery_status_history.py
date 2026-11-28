"""add delivery status history

Revision ID: ebb6498989ab
Revises: 717c163e271b
Create Date: 2026-11-28 17:28:16.692464

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ebb6498989ab"
down_revision: Union[str, Sequence[str], None] = "717c163e271b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the new delivery status history table only."""

    op.create_table(
        "delivery_status_history",
        sa.Column(
            "history_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "delivery_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "previous_status",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "new_status",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["deliveries.delivery_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("history_id"),
    )

    op.create_index(
        "ix_delivery_status_history_delivery_changed",
        "delivery_status_history",
        ["delivery_id", "changed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove only the objects created by this migration."""

    op.drop_index(
        "ix_delivery_status_history_delivery_changed",
        table_name="delivery_status_history",
    )

    op.drop_table("delivery_status_history")
