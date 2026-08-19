"""Tests for database models."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from taskowl.models import TaskEvent, WorkerEvent


@pytest.mark.asyncio
async def test_create_task_event(db_session):
    """Test creating a task event."""
    task_id = uuid.uuid4()
    event = TaskEvent(
        event_type="received",
        task_id=task_id,
        timestamp=datetime.now(UTC),
        hostname="worker1@localhost",
        name="test_task",
        args={"arg1": "value1"},
        kwargs={"kwarg1": "value2"},
        queue="default",
    )
    db_session.add(event)
    await db_session.commit()

    # Query the event
    result = await db_session.execute(select(TaskEvent).where(TaskEvent.task_id == task_id))
    retrieved_event = result.scalar_one()

    assert retrieved_event.event_type == "received"
    assert retrieved_event.task_id == task_id
    assert retrieved_event.name == "test_task"
    assert retrieved_event.hostname == "worker1@localhost"
    assert retrieved_event.args == {"arg1": "value1"}
    assert retrieved_event.kwargs == {"kwarg1": "value2"}
    assert retrieved_event.queue == "default"
    assert retrieved_event.created_at is not None


@pytest.mark.asyncio
async def test_create_worker_event(db_session):
    """Test creating a worker event."""
    event = WorkerEvent(
        event_type="heartbeat",
        hostname="worker1@localhost",
        timestamp=datetime.now(UTC),
        active=2,
        processed=100,
        freq=2.0,
        sw_ident="py-celery",
        sw_ver="5.6.3",
        sw_sys="Linux",
    )
    db_session.add(event)
    await db_session.commit()

    # Query the event
    result = await db_session.execute(
        select(WorkerEvent).where(WorkerEvent.hostname == event.hostname)
    )
    retrieved_event = result.scalar_one()

    assert retrieved_event.event_type == "heartbeat"
    assert retrieved_event.hostname == "worker1@localhost"
    assert retrieved_event.active == 2
    assert retrieved_event.processed == 100
    assert retrieved_event.freq == 2.0
    assert retrieved_event.sw_ident == "py-celery"
    assert retrieved_event.sw_ver == "5.6.3"
    assert retrieved_event.sw_sys == "Linux"


@pytest.mark.asyncio
async def test_task_event_timeline(db_session):
    """Test creating multiple events for a task (timeline)."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Create received event
    event1 = TaskEvent(
        event_type="received",
        task_id=task_id,
        timestamp=now,
        hostname="worker1@localhost",
        name="test_task",
    )
    db_session.add(event1)
    await db_session.commit()

    # Create started event
    event2 = TaskEvent(
        event_type="started",
        task_id=task_id,
        timestamp=now + timedelta(microseconds=1000),
        hostname="worker1@localhost",
        pid=12345,
    )
    db_session.add(event2)
    await db_session.commit()

    # Create succeeded event
    event3 = TaskEvent(
        event_type="succeeded",
        task_id=task_id,
        timestamp=now + timedelta(microseconds=2000),
        hostname="worker1@localhost",
        runtime=1.5,
        result={"status": "ok"},
    )
    db_session.add(event3)
    await db_session.commit()

    # Query all events for this task
    result = await db_session.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.timestamp)
    )
    events = result.scalars().all()

    assert len(events) == 3
    assert events[0].event_type == "received"
    assert events[1].event_type == "started"
    assert events[1].pid == 12345
    assert events[2].event_type == "succeeded"
    assert events[2].runtime == 1.5
    assert events[2].result == {"status": "ok"}
