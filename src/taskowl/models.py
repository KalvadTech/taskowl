import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from taskowl.database import Base


class TaskEvent(Base):
    """Append-only event log for Celery task events."""

    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Event-specific fields (nullable, only populated for relevant events)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    kwargs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    exception: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime: Mapped[float | None] = mapped_column(Float, nullable=True)
    retries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    root_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signum: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terminated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    expired: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    requeue: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_task_events_task_id_timestamp", "task_id", "timestamp"),
        Index("idx_task_events_event_type_timestamp", "event_type", "timestamp"),
        Index("idx_task_events_timestamp", "timestamp"),
    )


class WorkerEvent(Base):
    """Append-only event log for Celery worker events."""

    __tablename__ = "worker_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Heartbeat-specific fields
    active: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    freq: Mapped[float | None] = mapped_column(Float, nullable=True)
    sw_ident: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sw_ver: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sw_sys: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_worker_events_hostname_timestamp", "hostname", "timestamp"),
        Index("idx_worker_events_event_type_timestamp", "event_type", "timestamp"),
        Index("idx_worker_events_timestamp", "timestamp"),
    )


class Automation(Base):
    """Declarative workflow automation definition.

    An automation evaluates Celery events (or runs on a schedule) and, when
    its conditions match, fires a list of actions. It is the general
    superset of the original env-var alerts.
    """

    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Trigger: "event" (fire on a Celery event type) or "periodic" (on a schedule)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    schedule_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Conditions and actions as declarative JSON lists
    conditions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    actions: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Safety: prevent storming
    cooldown_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_runs_per_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    window_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optional per-automation circuit breaker
    circuit_breaker: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
        Index("idx_automations_enabled", "enabled"),
        Index("idx_automations_trigger", "trigger_type"),
    )


class AutomationRun(Base):
    """Append-only audit log of automation evaluations and fired actions."""

    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    automation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conditions_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actions_fired: Mapped[list | None] = mapped_column(JSON, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_automation_runs_automation_id", "automation_id"),
        Index("idx_automation_runs_created_at", "created_at"),
    )
