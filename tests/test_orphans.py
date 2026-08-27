"""Tests for orphaned task detection."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.models import TaskEvent, WorkerEvent
from taskowl.queries import _worker_is_offline, list_orphaned_tasks_query


@pytest.mark.asyncio
async def test_worker_is_offline_no_events(db_session: AsyncSession):
    """Worker with no events should be considered offline."""
    result = await _worker_is_offline(
        db_session,
        "worker1@localhost",
        datetime.now(UTC),
        timedelta(seconds=30),
    )
    assert result is True


@pytest.mark.asyncio
async def test_worker_is_offline_offline_event(db_session: AsyncSession):
    """Worker with an offline event should be offline."""
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=datetime.now(UTC),
        )
    )
    await db_session.commit()

    result = await _worker_is_offline(
        db_session,
        "worker1@localhost",
        datetime.now(UTC),
        timedelta(seconds=30),
    )
    assert result is True


@pytest.mark.asyncio
async def test_worker_is_offline_stale_heartbeat(db_session: AsyncSession):
    """Worker with a stale heartbeat should be offline."""
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker1@localhost",
            timestamp=datetime.now(UTC) - timedelta(seconds=120),
        )
    )
    await db_session.commit()

    result = await _worker_is_offline(
        db_session,
        "worker1@localhost",
        datetime.now(UTC),
        timedelta(seconds=30),
    )
    assert result is True


@pytest.mark.asyncio
async def test_worker_is_offline_recent_heartbeat(db_session: AsyncSession):
    """Worker with a recent heartbeat should be online."""
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker1@localhost",
            timestamp=datetime.now(UTC) - timedelta(seconds=5),
        )
    )
    await db_session.commit()

    result = await _worker_is_offline(
        db_session,
        "worker1@localhost",
        datetime.now(UTC),
        timedelta(seconds=30),
    )
    assert result is False


@pytest.mark.asyncio
async def test_orphaned_task_detected(db_session: AsyncSession):
    """Task started > grace with offline worker should be orphaned."""
    now = datetime.now(UTC)
    task_id = uuid.uuid4()

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now - timedelta(seconds=301),
            hostname="worker1@localhost",
            name="myapp.tasks.orphaned_job",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now - timedelta(seconds=300),
            hostname="worker1@localhost",
        )
    )
    # Worker went offline long ago
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    await db_session.commit()

    result = await list_orphaned_tasks_query(limit=10, session=db_session)
    assert len(result) == 1
    assert result[0]["state"] == "orphaned"
    assert result[0]["worker"] == "worker1@localhost"
    # name is reconstructed from the 'received' event
    assert result[0]["name"] == "myapp.tasks.orphaned_job"


@pytest.mark.asyncio
async def test_not_orphaned_within_grace_period(db_session: AsyncSession):
    """Task started within grace period should not be orphaned yet."""
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=uuid.uuid4(),
            timestamp=now - timedelta(seconds=5),
            hostname="worker1@localhost",
        )
    )
    # Worker offline but task started recently
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=10),
        )
    )
    await db_session.commit()

    result = await list_orphaned_tasks_query(limit=10, session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_not_orphaned_worker_online(db_session: AsyncSession):
    """Task started > grace with online worker should not be orphaned."""
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=uuid.uuid4(),
            timestamp=now - timedelta(seconds=300),
            hostname="worker1@localhost",
        )
    )
    # Worker still sending heartbeats
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=5),
        )
    )
    await db_session.commit()

    result = await list_orphaned_tasks_query(limit=10, session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_not_orphaned_terminal_event(db_session: AsyncSession):
    """Task with a terminal event should not be orphaned."""
    now = datetime.now(UTC)
    task_id = uuid.uuid4()

    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now - timedelta(seconds=300),
            hostname="worker1@localhost",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now - timedelta(seconds=200),
            hostname="worker1@localhost",
        )
    )
    # Worker offline but task already completed
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    await db_session.commit()

    result = await list_orphaned_tasks_query(limit=10, session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_multiple_tasks_only_orphaned_returned(db_session: AsyncSession):
    """Only the orphaned task among several should be returned."""
    now = datetime.now(UTC)
    orphan_id = uuid.uuid4()
    healthy_id = uuid.uuid4()

    # Orphaned task
    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=orphan_id,
            timestamp=now - timedelta(seconds=300),
            hostname="worker1@localhost",
        )
    )
    # Healthy task (worker online)
    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=healthy_id,
            timestamp=now - timedelta(seconds=300),
            hostname="worker2@localhost",
        )
    )
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker2@localhost",
            timestamp=now - timedelta(seconds=5),
        )
    )
    await db_session.commit()

    result = await list_orphaned_tasks_query(limit=10, session=db_session)
    assert len(result) == 1
    assert result[0]["id"] == str(orphan_id)
