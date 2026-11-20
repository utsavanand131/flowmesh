"""add created_at to orders

Revision ID: 540ab80cb2de
Revises: c6a8164fa1b0
Create Date: 2026-11-20 17:30:39.638873

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "540ab80cb2de"
down_revision: Union[str, Sequence[str], None] = "c6a8164fa1b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add created_at with a temporary server default so existing
    # orders receive a timestamp without losing any records.
    op.add_column(
        "orders",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    # Only removes the column introduced by this migration.
    op.drop_column("orders", "created_at")
