"""Event handlers for Celery events.

This module contains handler functions for each Celery event type.
Each handler creates a TaskEvent or WorkerEvent record and inserts it into the database.

Inserts are idempotent: every row carries a deterministic ``dedupe_key`` and
is written with ``INSERT ... ON CONFLICT DO NOTHING`` so that broker
redeliveries and consumer replays do not create duplicate rows. Events emitted
without a timestamp cannot be keyed deterministically and are written with a
NULL key (always inserted).
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.models import TaskEvent, WorkerEvent

logger = logging.getLogger(__name__)


def _parse_timestamp(timestamp: float | None) -> datetime | None:
    """Parse Celery timestamp (Unix epoch) to datetime."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    """Parse UUID string to UUID object."""
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError, AttributeError:
        return None


def _event_timestamp(event: dict) -> datetime | None:
    """Return the event's own timestamp, or None when the event has none."""
    return _parse_timestamp(event.get("timestamp"))


def _dedupe_key(*parts: object) -> str:
    """Build a deterministic sha256 key from the given parts."""
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _task_dedupe_key(
    event_type: str,
    task_id: uuid.UUID,
    hostname: str | None,
    source_ts: datetime | None,
) -> str | None:
    """Deterministic key for a task event; None when the event has no timestamp."""
    if source_ts is None:
        return None
    return _dedupe_key(event_type, task_id, hostname, source_ts.isoformat())


def _worker_dedupe_key(
    event_type: str,
    hostname: str,
    source_ts: datetime | None,
) -> str | None:
    """Deterministic key for a worker event; None when the event has no timestamp."""
    if source_ts is None:
        return None
    return _dedupe_key(event_type, hostname, source_ts.isoformat())


async def insert_event(session: AsyncSession, model: type[Any], values: dict[str, Any]) -> None:
    """Insert an event row, silently ignoring duplicates by ``dedupe_key``.

    Uses the active dialect's ``INSERT ... ON CONFLICT DO NOTHING`` so that
    replaying the same event never creates a second row. Rows whose
    ``dedupe_key`` is NULL are always inserted (NULLs never conflict).
    """
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    statement = insert(model).values(**values).on_conflict_do_nothing(index_elements=["dedupe_key"])
    await session.execute(statement)
    await session.commit()


async def handle_task_sent(event: dict, session: AsyncSession) -> None:
    """Handle task-sent event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "sent",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "name": event.get("name"),
            "args": event.get("args"),
            "kwargs": event.get("kwargs"),
            "retries": event.get("retries"),
            "eta": _parse_timestamp(event.get("eta")),
            "expires": _parse_timestamp(event.get("expires")),
            "queue": event.get("queue"),
            "root_id": _parse_uuid(event.get("root_id")),
            "parent_id": _parse_uuid(event.get("parent_id")),
            "dedupe_key": _task_dedupe_key("sent", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_task_received(event: dict, session: AsyncSession) -> None:
    """Handle task-received event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "received",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "name": event.get("name"),
            "args": event.get("args"),
            "kwargs": event.get("kwargs"),
            "retries": event.get("retries"),
            "eta": _parse_timestamp(event.get("eta")),
            "expires": _parse_timestamp(event.get("expires")),
            "queue": event.get("queue"),
            "root_id": _parse_uuid(event.get("root_id")),
            "parent_id": _parse_uuid(event.get("parent_id")),
            "dedupe_key": _task_dedupe_key("received", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_task_started(event: dict, session: AsyncSession) -> None:
    """Handle task-started event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "started",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "pid": event.get("pid"),
            "dedupe_key": _task_dedupe_key("started", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_task_succeeded(event: dict, session: AsyncSession) -> None:
    """Handle task-succeeded event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "succeeded",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "result": event.get("result"),
            "runtime": event.get("runtime"),
            "dedupe_key": _task_dedupe_key("succeeded", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_task_failed(event: dict, session: AsyncSession) -> None:
    """Handle task-failed event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "failed",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "exception": event.get("exception"),
            "traceback": event.get("traceback"),
            "dedupe_key": _task_dedupe_key("failed", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_task_revoked(event: dict, session: AsyncSession) -> None:
    """Handle task-revoked event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "revoked",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "terminated": event.get("terminated"),
            "signum": event.get("signum"),
            "expired": event.get("expired"),
            "dedupe_key": _task_dedupe_key("revoked", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_task_retried(event: dict, session: AsyncSession) -> None:
    """Handle task-retried event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "retried",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "exception": event.get("exception"),
            "traceback": event.get("traceback"),
            "dedupe_key": _task_dedupe_key("retried", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_task_rejected(event: dict, session: AsyncSession) -> None:
    """Handle task-rejected event."""
    source_ts = _event_timestamp(event)
    task_id = uuid.UUID(event["uuid"])
    await insert_event(
        session,
        TaskEvent,
        {
            "event_type": "rejected",
            "task_id": task_id,
            "timestamp": source_ts or datetime.now(UTC),
            "hostname": event.get("hostname"),
            "requeue": event.get("requeue"),
            "dedupe_key": _task_dedupe_key("rejected", task_id, event.get("hostname"), source_ts),
        },
    )


async def handle_worker_online(event: dict, session: AsyncSession) -> None:
    """Handle worker-online event."""
    source_ts = _event_timestamp(event)
    hostname = event["hostname"]
    await insert_event(
        session,
        WorkerEvent,
        {
            "event_type": "online",
            "hostname": hostname,
            "timestamp": source_ts or datetime.now(UTC),
            "freq": event.get("freq"),
            "sw_ident": event.get("sw_ident"),
            "sw_ver": event.get("sw_ver"),
            "sw_sys": event.get("sw_sys"),
            "dedupe_key": _worker_dedupe_key("online", hostname, source_ts),
        },
    )


async def handle_worker_heartbeat(event: dict, session: AsyncSession) -> None:
    """Handle worker-heartbeat event."""
    source_ts = _event_timestamp(event)
    hostname = event["hostname"]
    await insert_event(
        session,
        WorkerEvent,
        {
            "event_type": "heartbeat",
            "hostname": hostname,
            "timestamp": source_ts or datetime.now(UTC),
            "active": event.get("active"),
            "processed": event.get("processed"),
            "freq": event.get("freq"),
            "sw_ident": event.get("sw_ident"),
            "sw_ver": event.get("sw_ver"),
            "sw_sys": event.get("sw_sys"),
            "dedupe_key": _worker_dedupe_key("heartbeat", hostname, source_ts),
        },
    )


async def handle_worker_offline(event: dict, session: AsyncSession) -> None:
    """Handle worker-offline event."""
    source_ts = _event_timestamp(event)
    hostname = event["hostname"]
    await insert_event(
        session,
        WorkerEvent,
        {
            "event_type": "offline",
            "hostname": hostname,
            "timestamp": source_ts or datetime.now(UTC),
            "freq": event.get("freq"),
            "sw_ident": event.get("sw_ident"),
            "sw_ver": event.get("sw_ver"),
            "sw_sys": event.get("sw_sys"),
            "dedupe_key": _worker_dedupe_key("offline", hostname, source_ts),
        },
    )


# Handler mapping for easy lookup
TASK_EVENT_HANDLERS = {
    "task-sent": handle_task_sent,
    "task-received": handle_task_received,
    "task-started": handle_task_started,
    "task-succeeded": handle_task_succeeded,
    "task-failed": handle_task_failed,
    "task-revoked": handle_task_revoked,
    "task-retried": handle_task_retried,
    "task-rejected": handle_task_rejected,
}

WORKER_EVENT_HANDLERS = {
    "worker-online": handle_worker_online,
    "worker-heartbeat": handle_worker_heartbeat,
    "worker-offline": handle_worker_offline,
}
