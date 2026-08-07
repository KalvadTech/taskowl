import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from taskowl.database import Base


class Task(Base):
    """Celery task model."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    kwargs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker: Mapped[str | None] = mapped_column(String(255), nullable=True)
    queue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    runtime: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_tasks_state", "state"),
        Index("idx_tasks_name", "name"),
        Index("idx_tasks_worker", "worker"),
        Index("idx_tasks_created_at", "created_at"),
        Index("idx_tasks_finished_at", "finished_at"),
    )


class Worker(Base):
    """Celery worker model."""

    __tablename__ = "workers"

    hostname: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="offline")
    pool_size: Mapped[int | None] = mapped_column(nullable=True)
    active_count: Mapped[int | None] = mapped_column(nullable=True)
    processed_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    loadavg: Mapped[list[float] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
