
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Delivery(Base):
    __tablename__ = "deliveries"

    delivery_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    order_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ASSIGNED",
    )


class OutboxEvent(Base):
    __tablename__ = "delivery_outbox_events"

    event_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    aggregate_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    aggregate_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
