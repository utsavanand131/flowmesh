"""add created_at to deliveries

Revision ID: 717c163e271b
Revises: 540ab80cb2de
Create Date: 2026-11-21 16:26:34.888322
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "717c163e271b"
down_revision: Union[str, Sequence[str], None] = "540ab80cb2de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "deliveries",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("deliveries", "created_at")
