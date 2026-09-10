from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

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