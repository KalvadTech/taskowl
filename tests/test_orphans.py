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


@pytest.mark.asyncio
async def test_orphan_worker_check_is_batched(db_session: AsyncSession):
    """The worker-offline check must be a single query, not one per task (N+1)."""
    from sqlalchemy import event

    now = datetime.now(UTC)
    # Several orphaned tasks all on the same offline worker
    for _ in range(5):
        db_session.add(
            TaskEvent(
                event_type="started",
                task_id=uuid.uuid4(),
                timestamp=now - timedelta(seconds=300),
                hostname="worker1@localhost",
            )
        )
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    await db_session.commit()

    query_count = 0

    def _count_queries(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        if statement.lstrip().upper().startswith("SELECT"):
            query_count += 1

    event.listen(db_session.get_bind(), "before_cursor_execute", _count_queries)
    try:
        result = await list_orphaned_tasks_query(limit=10, session=db_session)
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", _count_queries)

    assert len(result) == 5
    # Windowed latest-events query + batched worker-offline query (no per-task queries)
    assert query_count == 2


@pytest.mark.asyncio
async def test_orphan_same_timestamp_no_duplicates(db_session: AsyncSession):
    """Two orphan-candidate events for one task at the same timestamp must yield one row."""
    now = datetime.now(UTC)
    task_id = uuid.uuid4()

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now - timedelta(seconds=301),
            hostname="worker1@localhost",
            name="dup_orphan",
        )
    )
    await db_session.commit()
    # Two 'started' events at the exact same timestamp — both orphan candidates
    for _ in range(2):
        db_session.add(
            TaskEvent(
                event_type="started",
                task_id=task_id,
                timestamp=now - timedelta(seconds=300),
                hostname="worker1@localhost",
            )
        )
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
    assert result[0]["id"] == str(task_id)
