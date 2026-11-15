from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    product_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    reservation_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    product_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="RESERVED",
    )
