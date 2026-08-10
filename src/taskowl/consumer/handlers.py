"""Event handlers for Celery events.

This module contains handler functions for each Celery event type.
Each handler creates a TaskEvent or WorkerEvent record and inserts it into the database.
"""

import logging
import uuid
from datetime import UTC, datetime

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


async def handle_task_sent(event: dict, session: AsyncSession) -> None:
    """Handle task-sent event."""
    task_event = TaskEvent(
        event_type="sent",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        name=event.get("name"),
        args=event.get("args"),
        kwargs=event.get("kwargs"),
        retries=event.get("retries"),
        eta=_parse_timestamp(event.get("eta")),
        expires=_parse_timestamp(event.get("expires")),
        queue=event.get("queue"),
        root_id=_parse_uuid(event.get("root_id")),
        parent_id=_parse_uuid(event.get("parent_id")),
    )
    session.add(task_event)
    await session.commit()


async def handle_task_received(event: dict, session: AsyncSession) -> None:
    """Handle task-received event."""
    task_event = TaskEvent(
        event_type="received",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        name=event.get("name"),
        args=event.get("args"),
        kwargs=event.get("kwargs"),
        retries=event.get("retries"),
        eta=_parse_timestamp(event.get("eta")),
        expires=_parse_timestamp(event.get("expires")),
        queue=event.get("queue"),
        root_id=_parse_uuid(event.get("root_id")),
        parent_id=_parse_uuid(event.get("parent_id")),
    )
    session.add(task_event)
    await session.commit()


async def handle_task_started(event: dict, session: AsyncSession) -> None:
    """Handle task-started event."""
    task_event = TaskEvent(
        event_type="started",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        pid=event.get("pid"),
    )
    session.add(task_event)
    await session.commit()


async def handle_task_succeeded(event: dict, session: AsyncSession) -> None:
    """Handle task-succeeded event."""
    task_event = TaskEvent(
        event_type="succeeded",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        result=event.get("result"),
        runtime=event.get("runtime"),
    )
    session.add(task_event)
    await session.commit()


async def handle_task_failed(event: dict, session: AsyncSession) -> None:
    """Handle task-failed event."""
    task_event = TaskEvent(
        event_type="failed",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        exception=event.get("exception"),
        traceback=event.get("traceback"),
    )
    session.add(task_event)
    await session.commit()


async def handle_task_revoked(event: dict, session: AsyncSession) -> None:
    """Handle task-revoked event."""
    task_event = TaskEvent(
        event_type="revoked",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        terminated=event.get("terminated"),
        signum=event.get("signum"),
        expired=event.get("expired"),
    )
    session.add(task_event)
    await session.commit()


async def handle_task_retried(event: dict, session: AsyncSession) -> None:
    """Handle task-retried event."""
    task_event = TaskEvent(
        event_type="retried",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        exception=event.get("exception"),
        traceback=event.get("traceback"),
    )
    session.add(task_event)
    await session.commit()


async def handle_task_rejected(event: dict, session: AsyncSession) -> None:
    """Handle task-rejected event."""
    task_event = TaskEvent(
        event_type="rejected",
        task_id=uuid.UUID(event["uuid"]),
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        hostname=event.get("hostname"),
        requeue=event.get("requeue"),
    )
    session.add(task_event)
    await session.commit()


async def handle_worker_online(event: dict, session: AsyncSession) -> None:
    """Handle worker-online event."""
    worker_event = WorkerEvent(
        event_type="online",
        hostname=event["hostname"],
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        freq=event.get("freq"),
        sw_ident=event.get("sw_ident"),
        sw_ver=event.get("sw_ver"),
        sw_sys=event.get("sw_sys"),
    )
    session.add(worker_event)
    await session.commit()


async def handle_worker_heartbeat(event: dict, session: AsyncSession) -> None:
    """Handle worker-heartbeat event."""
    worker_event = WorkerEvent(
        event_type="heartbeat",
        hostname=event["hostname"],
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        active=event.get("active"),
        processed=event.get("processed"),
        freq=event.get("freq"),
        sw_ident=event.get("sw_ident"),
        sw_ver=event.get("sw_ver"),
        sw_sys=event.get("sw_sys"),
    )
    session.add(worker_event)
    await session.commit()


async def handle_worker_offline(event: dict, session: AsyncSession) -> None:
    """Handle worker-offline event."""
    worker_event = WorkerEvent(
        event_type="offline",
        hostname=event["hostname"],
        timestamp=_parse_timestamp(event.get("timestamp")) or datetime.now(UTC),
        freq=event.get("freq"),
        sw_ident=event.get("sw_ident"),
        sw_ver=event.get("sw_ver"),
        sw_sys=event.get("sw_sys"),
    )
    session.add(worker_event)
    await session.commit()


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
