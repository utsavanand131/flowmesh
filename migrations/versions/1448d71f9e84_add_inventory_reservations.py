"""add inventory reservations

Revision ID: 1448d71f9e84
Revises: 18013a21a9a4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "1448d71f9e84"
down_revision: Union[str, Sequence[str], None] = "18013a21a9a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inventory_reservations",
        sa.Column(
            "reservation_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="RESERVED",
        ),
        sa.PrimaryKeyConstraint("reservation_id"),
    )

    op.create_index(
        "ix_inventory_reservations_product_id",
        "inventory_reservations",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_reservations_product_id",
        table_name="inventory_reservations",
    )

    op.drop_table("inventory_reservations")
