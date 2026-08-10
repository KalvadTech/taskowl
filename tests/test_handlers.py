"""Tests for consumer event handlers."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.consumer.handlers import (
    _parse_timestamp,
    _parse_uuid,
    handle_task_failed,
    handle_task_received,
    handle_task_started,
    handle_task_succeeded,
    handle_worker_heartbeat,
    handle_worker_offline,
    handle_worker_online,
)
from taskowl.models import TaskEvent, WorkerEvent


def test_parse_timestamp_valid():
    """Test _parse_timestamp with valid timestamp."""
    ts = 1609459200.0  # 2021-01-01 00:00:00 UTC
    result = _parse_timestamp(ts)
    assert result is not None
    assert result.year == 2021
    assert result.month == 1
    assert result.day == 1
    assert result.tzinfo == UTC


def test_parse_timestamp_none():
    """Test _parse_timestamp with None."""
    result = _parse_timestamp(None)
    assert result is None


def test_parse_uuid_valid():
    """Test _parse_uuid with valid UUID string."""
    uuid_str = "12345678-1234-5678-1234-567812345678"
    result = _parse_uuid(uuid_str)
    assert result is not None
    assert str(result) == uuid_str


def test_parse_uuid_invalid():
    """Test _parse_uuid with invalid UUID string."""
    result = _parse_uuid("invalid-uuid")
    assert result is None


def test_parse_uuid_none():
    """Test _parse_uuid with None."""
    result = _parse_uuid(None)
    assert result is None


@pytest.mark.asyncio
async def test_handle_task_received(db_session: AsyncSession):
    """Test handle_task_received."""
    task_id = uuid.uuid4()
    event = {
        "uuid": str(task_id),
        "timestamp": datetime.now(UTC).timestamp(),
        "hostname": "worker1@localhost",
        "name": "test_task",
        "args": {"arg1": "value1"},
        "kwargs": {"kwarg1": "value2"},
        "retries": 0,
        "queue": "default",
    }

    await handle_task_received(event, db_session)

    # Verify event was created
    result = await db_session.execute(select(TaskEvent).where(TaskEvent.task_id == task_id))
    task_event = result.scalar_one()

    assert task_event.event_type == "received"
    assert task_event.task_id == task_id
    assert task_event.hostname == "worker1@localhost"
    assert task_event.name == "test_task"
    assert task_event.args == {"arg1": "value1"}
    assert task_event.kwargs == {"kwarg1": "value2"}
    assert task_event.retries == 0
    assert task_event.queue == "default"


@pytest.mark.asyncio
async def test_handle_task_started(db_session: AsyncSession):
    """Test handle_task_started."""
    task_id = uuid.uuid4()

    # First create a received event
    received_event = TaskEvent(
        event_type="received",
        task_id=task_id,
        timestamp=datetime.now(UTC),
        hostname="worker1@localhost",
        name="test_task",
    )
    db_session.add(received_event)
    await db_session.commit()

    # Now handle started event
    event = {
        "uuid": str(task_id),
        "timestamp": datetime.now(UTC).timestamp(),
        "hostname": "worker1@localhost",
        "pid": 12345,
    }

    await handle_task_started(event, db_session)

    # Verify started event was created
    result = await db_session.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id, TaskEvent.event_type == "started")
    )
    task_event = result.scalar_one()

    assert task_event.event_type == "started"
    assert task_event.task_id == task_id
    assert task_event.hostname == "worker1@localhost"
    assert task_event.pid == 12345


@pytest.mark.asyncio
async def test_handle_task_succeeded(db_session: AsyncSession):
    """Test handle_task_succeeded."""
    task_id = uuid.uuid4()

    # Create received and started events
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    # Handle succeeded event
    event = {
        "uuid": str(task_id),
        "timestamp": datetime.now(UTC).timestamp(),
        "hostname": "worker1@localhost",
        "result": {"status": "ok"},
        "runtime": 1.5,
    }

    await handle_task_succeeded(event, db_session)

    # Verify succeeded event was created
    result = await db_session.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id, TaskEvent.event_type == "succeeded")
    )
    task_event = result.scalar_one()

    assert task_event.event_type == "succeeded"
    assert task_event.task_id == task_id
    assert task_event.result == {"status": "ok"}
    assert task_event.runtime == 1.5


@pytest.mark.asyncio
async def test_handle_task_failed(db_session: AsyncSession):
    """Test handle_task_failed."""
    task_id = uuid.uuid4()

    # Create received and started events
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    # Handle failed event
    event = {
        "uuid": str(task_id),
        "timestamp": datetime.now(UTC).timestamp(),
        "hostname": "worker1@localhost",
        "exception": "ValueError",
        "traceback": "Traceback...",
    }

    await handle_task_failed(event, db_session)

    # Verify failed event was created
    result = await db_session.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id, TaskEvent.event_type == "failed")
    )
    task_event = result.scalar_one()

    assert task_event.event_type == "failed"
    assert task_event.task_id == task_id
    assert task_event.exception == "ValueError"
    assert task_event.traceback == "Traceback..."


@pytest.mark.asyncio
async def test_handle_worker_online(db_session: AsyncSession):
    """Test handle_worker_online."""
    event = {
        "hostname": "worker1@localhost",
        "timestamp": datetime.now(UTC).timestamp(),
        "freq": 2.0,
        "sw_ident": "py-celery",
        "sw_ver": "5.3.0",
        "sw_sys": "Linux",
    }

    await handle_worker_online(event, db_session)

    # Verify worker event was created
    result = await db_session.execute(
        select(WorkerEvent).where(WorkerEvent.hostname == "worker1@localhost")
    )
    worker_event = result.scalar_one()

    assert worker_event.event_type == "online"
    assert worker_event.hostname == "worker1@localhost"
    assert worker_event.freq == 2.0
    assert worker_event.sw_ident == "py-celery"
    assert worker_event.sw_ver == "5.3.0"
    assert worker_event.sw_sys == "Linux"


@pytest.mark.asyncio
async def test_handle_worker_heartbeat(db_session: AsyncSession):
    """Test handle_worker_heartbeat."""
    # First create an online event
    online_event = WorkerEvent(
        event_type="online",
        hostname="worker1@localhost",
        timestamp=datetime.now(UTC),
    )
    db_session.add(online_event)
    await db_session.commit()

    # Handle heartbeat event
    event = {
        "hostname": "worker1@localhost",
        "timestamp": datetime.now(UTC).timestamp(),
        "active": 2,
        "processed": 100,
        "freq": 2.0,
        "sw_ident": "py-celery",
        "sw_ver": "5.3.0",
        "sw_sys": "Linux",
    }

    await handle_worker_heartbeat(event, db_session)

    # Verify heartbeat event was created
    result = await db_session.execute(
        select(WorkerEvent).where(
            WorkerEvent.hostname == "worker1@localhost",
            WorkerEvent.event_type == "heartbeat",
        )
    )
    worker_event = result.scalar_one()

    assert worker_event.event_type == "heartbeat"
    assert worker_event.hostname == "worker1@localhost"
    assert worker_event.active == 2
    assert worker_event.processed == 100
    assert worker_event.freq == 2.0


@pytest.mark.asyncio
async def test_handle_worker_offline(db_session: AsyncSession):
    """Test handle_worker_offline."""
    # First create an online event
    online_event = WorkerEvent(
        event_type="online",
        hostname="worker1@localhost",
        timestamp=datetime.now(UTC),
    )
    db_session.add(online_event)
    await db_session.commit()

    # Handle offline event
    event = {
        "hostname": "worker1@localhost",
        "timestamp": datetime.now(UTC).timestamp(),
        "freq": 2.0,
        "sw_ident": "py-celery",
        "sw_ver": "5.3.0",
        "sw_sys": "Linux",
    }

    await handle_worker_offline(event, db_session)

    # Verify offline event was created
    result = await db_session.execute(
        select(WorkerEvent).where(
            WorkerEvent.hostname == "worker1@localhost",
            WorkerEvent.event_type == "offline",
        )
    )
    worker_event = result.scalar_one()

    assert worker_event.event_type == "offline"
    assert worker_event.hostname == "worker1@localhost"
