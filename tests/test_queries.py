"""Tests for query functions."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.models import TaskEvent, WorkerEvent
from taskowl.queries import (
    get_task_chain_query,
    get_task_query,
    get_task_summary_query,
    get_task_timeline_query,
    get_worker_status_query,
    list_task_types_query,
    list_tasks_query,
)


@pytest.mark.asyncio
async def test_list_tasks_empty(db_session: AsyncSession):
    """Test list_tasks_query with no data."""
    result = await list_tasks_query(session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_list_tasks_with_data(db_session: AsyncSession):
    """Test list_tasks_query with task events."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Create task events
    event1 = TaskEvent(
        event_type="received",
        task_id=task_id,
        timestamp=now,
        hostname="worker1@localhost",
        name="test_task",
    )
    db_session.add(event1)

    event2 = TaskEvent(
        event_type="succeeded",
        task_id=task_id,
        timestamp=now + timedelta(seconds=1),
        hostname="worker1@localhost",
        runtime=1.5,
    )
    db_session.add(event2)
    await db_session.commit()

    result = await list_tasks_query(session=db_session)
    assert len(result) == 1
    assert result[0]["id"] == str(task_id)
    assert result[0]["state"] == "succeeded"  # Latest state
    # name is reconstructed from the earliest event that carries it ('received')
    assert result[0]["name"] == "test_task"
    assert result[0]["worker"] == "worker1@localhost"


@pytest.mark.asyncio
async def test_list_tasks_filter_by_name_completed(db_session: AsyncSession):
    """Name filter should match completed tasks (name lives on 'received')."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="myapp.tasks.process",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    result = await list_tasks_query(name="myapp.tasks.process", session=db_session)
    assert len(result) == 1
    assert result[0]["name"] == "myapp.tasks.process"

    # Filter with a non-matching name should return nothing
    result = await list_tasks_query(name="other.task", session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_list_tasks_filter_by_state(db_session: AsyncSession):
    """Test list_tasks_query with state filter."""
    task1_id = uuid.uuid4()
    task2_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Task 1: succeeded
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task1_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )

    # Task 2: failed
    db_session.add(
        TaskEvent(
            event_type="failed",
            task_id=task2_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    # Filter by succeeded
    result = await list_tasks_query(state="succeeded", session=db_session)
    assert len(result) == 1
    assert result[0]["id"] == str(task1_id)

    # Filter by failed
    result = await list_tasks_query(state="failed", session=db_session)
    assert len(result) == 1
    assert result[0]["id"] == str(task2_id)


@pytest.mark.asyncio
async def test_list_tasks_filter_by_name(db_session: AsyncSession):
    """Test list_tasks_query with name filter."""
    task1_id = uuid.uuid4()
    task2_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task1_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="task_a",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task2_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="task_b",
        )
    )
    await db_session.commit()

    result = await list_tasks_query(name="task_a", session=db_session)
    assert len(result) == 1
    assert result[0]["name"] == "task_a"


@pytest.mark.asyncio
async def test_list_tasks_filter_by_worker(db_session: AsyncSession):
    """Test list_tasks_query with worker filter."""
    task1_id = uuid.uuid4()
    task2_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task1_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task2_id,
            timestamp=now,
            hostname="worker2@localhost",
        )
    )
    await db_session.commit()

    result = await list_tasks_query(worker="worker1@localhost", session=db_session)
    assert len(result) == 1
    assert result[0]["worker"] == "worker1@localhost"


@pytest.mark.asyncio
async def test_list_tasks_filter_by_since(db_session: AsyncSession):
    """Test list_tasks_query with since filter."""
    task1_id = uuid.uuid4()
    task2_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Old task
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task1_id,
            timestamp=now - timedelta(hours=2),
            hostname="worker1@localhost",
        )
    )

    # Recent task
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task2_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    # Filter tasks from last hour
    since = (now - timedelta(hours=1)).isoformat()
    result = await list_tasks_query(since=since, session=db_session)
    assert len(result) == 1
    assert result[0]["id"] == str(task2_id)


@pytest.mark.asyncio
async def test_list_tasks_limit(db_session: AsyncSession):
    """Test list_tasks_query with limit."""
    now = datetime.now(UTC)

    # Create 5 tasks
    for i in range(5):
        db_session.add(
            TaskEvent(
                event_type="received",
                task_id=uuid.uuid4(),
                timestamp=now + timedelta(seconds=i),
                hostname="worker1@localhost",
            )
        )
    await db_session.commit()

    result = await list_tasks_query(limit=3, session=db_session)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_tasks_filter_by_search(db_session: AsyncSession):
    """Test list_tasks_query with partial search filter."""
    task1_id = uuid.uuid4()
    task2_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task1_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="myapp.tasks.process",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task2_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="other.module.cleanup",
        )
    )
    await db_session.commit()

    # Partial, case-insensitive match
    result = await list_tasks_query(search="PROCESS", session=db_session)
    assert len(result) == 1
    assert result[0]["id"] == str(task1_id)

    # No match
    result = await list_tasks_query(search="nonexistent", session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_list_tasks_offset(db_session: AsyncSession):
    """Test list_tasks_query with offset pagination."""
    now = datetime.now(UTC)
    task_ids = []
    for i in range(5):
        task_id = uuid.uuid4()
        task_ids.append(str(task_id))
        db_session.add(
            TaskEvent(
                event_type="received",
                task_id=task_id,
                timestamp=now + timedelta(seconds=i),
                hostname="worker1@localhost",
            )
        )
    await db_session.commit()

    # Default sort is newest-first, so skipping 2 skips the 2 newest
    result = await list_tasks_query(limit=10, offset=2, session=db_session)
    assert len(result) == 3
    assert result[0]["id"] not in task_ids[3:]


@pytest.mark.asyncio
async def test_list_tasks_sort_by_name(db_session: AsyncSession):
    """Test list_tasks_query sorted by name."""
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now,
            hostname="worker1@localhost",
            name="zeta",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now,
            hostname="worker1@localhost",
            name="alpha",
        )
    )
    await db_session.commit()

    result = await list_tasks_query(sort_by="name", session=db_session)
    assert len(result) == 2
    assert result[0]["name"] == "alpha"
    assert result[1]["name"] == "zeta"


@pytest.mark.asyncio
async def test_list_tasks_invalid_sort_by(db_session: AsyncSession):
    """Test list_tasks_query with invalid sort_by."""
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=datetime.now(UTC),
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    result = await list_tasks_query(sort_by="bogus", session=db_session)
    assert "error" in result


@pytest.mark.asyncio
async def test_list_task_types(db_session: AsyncSession):
    """Test list_task_types_query returns distinct names with counts."""
    now = datetime.now(UTC)
    for name, count in [("app.tasks.a", 2), ("app.tasks.b", 1)]:
        for _ in range(count):
            db_session.add(
                TaskEvent(
                    event_type="received",
                    task_id=uuid.uuid4(),
                    timestamp=now,
                    hostname="worker1@localhost",
                    name=name,
                )
            )
    await db_session.commit()

    result = await list_task_types_query(session=db_session)
    assert len(result) == 2
    by_name = {r["name"]: r["count"] for r in result}
    assert by_name["app.tasks.a"] == 2
    assert by_name["app.tasks.b"] == 1
    # Ordered by count desc
    assert result[0]["name"] == "app.tasks.a"


@pytest.mark.asyncio
async def test_list_task_types_empty(db_session: AsyncSession):
    """Test list_task_types_query with no data."""
    result = await list_task_types_query(session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_get_task_success(db_session: AsyncSession):
    """Test get_task_query with valid task."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Create task lifecycle
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
            args={"arg1": "value1"},
        )
    )

    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now + timedelta(seconds=2),
            hostname="worker1@localhost",
            runtime=1.5,
            result={"status": "ok"},
        )
    )
    await db_session.commit()

    result = await get_task_query(str(task_id), session=db_session)
    assert result["id"] == str(task_id)
    assert result["state"] == "succeeded"
    assert result["name"] == "test_task"
    assert result["args"] == {"arg1": "value1"}
    assert result["runtime"] == 1.5
    assert result["result"] == {"status": "ok"}
    assert len(result["events"]) == 3
    assert result["events"][0]["event_type"] == "received"
    assert result["events"][1]["event_type"] == "started"
    assert result["events"][2]["event_type"] == "succeeded"


@pytest.mark.asyncio
async def test_get_task_invalid_uuid(db_session: AsyncSession):
    """Test get_task_query with invalid UUID."""
    result = await get_task_query("invalid-uuid", session=db_session)
    assert "error" in result
    assert "Invalid task_id format" in result["error"]


@pytest.mark.asyncio
async def test_get_task_not_found(db_session: AsyncSession):
    """Test get_task_query with non-existent task."""
    task_id = uuid.uuid4()
    result = await get_task_query(str(task_id), session=db_session)
    assert "error" in result
    assert "Task not found" in result["error"]


@pytest.mark.asyncio
async def test_get_task_timeline_success(db_session: AsyncSession):
    """Test get_task_timeline_query with valid task."""
    task_id = uuid.uuid4()
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
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now + timedelta(seconds=2),
            hostname="worker1@localhost",
            runtime=1.5,
        )
    )
    await db_session.commit()

    result = await get_task_timeline_query(str(task_id), session=db_session)
    assert len(result) == 3
    assert result[0]["event_type"] == "received"
    assert result[0]["details"]["name"] == "test_task"
    assert result[1]["event_type"] == "started"
    assert result[2]["event_type"] == "succeeded"
    assert result[2]["details"]["runtime"] == 1.5


@pytest.mark.asyncio
async def test_get_task_timeline_invalid_uuid(db_session: AsyncSession):
    """Test get_task_timeline_query with invalid UUID."""
    result = await get_task_timeline_query("invalid-uuid", session=db_session)
    assert len(result) == 1
    assert "error" in result[0]
    assert "Invalid task_id format" in result[0]["error"]


@pytest.mark.asyncio
async def test_get_task_timeline_not_found(db_session: AsyncSession):
    """Test get_task_timeline_query with non-existent task."""
    task_id = uuid.uuid4()
    result = await get_task_timeline_query(str(task_id), session=db_session)
    assert len(result) == 1
    assert "error" in result[0]
    assert "Task not found" in result[0]["error"]


@pytest.mark.asyncio
async def test_get_task_summary_empty(db_session: AsyncSession):
    """Test get_task_summary_query with no data."""
    result = await get_task_summary_query(hours=1, session=db_session)
    assert result["total_tasks"] == 0
    assert result["by_state"] == {}
    assert result["avg_runtime_seconds"] is None


@pytest.mark.asyncio
async def test_get_task_summary_with_data(db_session: AsyncSession):
    """Test get_task_summary_query with task data."""
    now = datetime.now(UTC)

    # Create 3 succeeded tasks
    for i in range(3):
        db_session.add(
            TaskEvent(
                event_type="succeeded",
                task_id=uuid.uuid4(),
                timestamp=now,
                hostname="worker1@localhost",
                runtime=1.0 + i,
            )
        )

    # Create 2 failed tasks
    for _ in range(2):
        db_session.add(
            TaskEvent(
                event_type="failed",
                task_id=uuid.uuid4(),
                timestamp=now,
                hostname="worker1@localhost",
            )
        )
    await db_session.commit()

    result = await get_task_summary_query(hours=1, session=db_session)
    assert result["total_tasks"] == 5
    assert result["by_state"]["succeeded"] == 3
    assert result["by_state"]["failed"] == 2
    assert result["avg_runtime_seconds"] == 2.0  # (1.0 + 2.0 + 3.0) / 3


@pytest.mark.asyncio
async def test_get_task_summary_custom_hours(db_session: AsyncSession):
    """Test get_task_summary_query with custom time window."""
    now = datetime.now(UTC)

    # Old task (3 hours ago)
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=uuid.uuid4(),
            timestamp=now - timedelta(hours=3),
            hostname="worker1@localhost",
        )
    )

    # Recent task (30 minutes ago)
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=uuid.uuid4(),
            timestamp=now - timedelta(minutes=30),
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    # Last hour should only include recent task
    result = await get_task_summary_query(hours=1, session=db_session)
    assert result["total_tasks"] == 1

    # Last 4 hours should include both tasks
    result = await get_task_summary_query(hours=4, session=db_session)
    assert result["total_tasks"] == 2


@pytest.mark.asyncio
async def test_get_worker_status_empty(db_session: AsyncSession):
    """Test get_worker_status_query with no data."""
    result = await get_worker_status_query(session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_get_worker_status_with_data(db_session: AsyncSession):
    """Test get_worker_status_query with worker events."""
    now = datetime.now(UTC)

    # Worker 1: online then heartbeat
    db_session.add(
        WorkerEvent(
            event_type="online",
            hostname="worker1@localhost",
            timestamp=now,
            sw_ident="py-celery",
            sw_ver="5.3.0",
        )
    )

    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker1@localhost",
            timestamp=now + timedelta(seconds=10),
            active=2,
            processed=100,
        )
    )

    # Worker 2: online
    db_session.add(
        WorkerEvent(
            event_type="online",
            hostname="worker2@localhost",
            timestamp=now,
        )
    )
    await db_session.commit()

    result = await get_worker_status_query(session=db_session)
    assert len(result) == 2

    # Find worker1
    worker1 = next(w for w in result if w["hostname"] == "worker1@localhost")
    assert worker1["status"] == "online"  # Recent heartbeat
    assert worker1["last_event"] == "heartbeat"
    assert worker1["active"] == 2
    assert worker1["processed"] == 100
    # Note: sw_ident, sw_ver, sw_sys are only in the "online" event, not in "heartbeat"
    # The query returns the latest event's data, so these fields won't be present
    assert "sw_ident" not in worker1

    # Find worker2
    worker2 = next(w for w in result if w["hostname"] == "worker2@localhost")
    assert worker2["status"] == "online"


@pytest.mark.asyncio
async def test_worker_status_stale_heartbeat(db_session: AsyncSession):
    """Worker with a stale heartbeat should be offline."""
    now = datetime.now(UTC)
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    await db_session.commit()

    result = await get_worker_status_query(session=db_session)
    assert len(result) == 1
    assert result[0]["status"] == "offline"
    assert result[0]["last_event"] == "heartbeat"


@pytest.mark.asyncio
async def test_worker_status_explicit_offline(db_session: AsyncSession):
    """Worker with an explicit offline event should be offline."""
    now = datetime.now(UTC)
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now,
        )
    )
    await db_session.commit()

    result = await get_worker_status_query(session=db_session)
    assert len(result) == 1
    assert result[0]["status"] == "offline"
    assert result[0]["last_event"] == "offline"


@pytest.mark.asyncio
async def test_worker_status_recent_online(db_session: AsyncSession):
    """Worker with a recent online event should be online."""
    now = datetime.now(UTC)
    db_session.add(
        WorkerEvent(
            event_type="online",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=5),
        )
    )
    await db_session.commit()

    result = await get_worker_status_query(session=db_session)
    assert len(result) == 1
    assert result[0]["status"] == "online"


@pytest.mark.asyncio
async def test_worker_status_unknown_when_no_events(db_session: AsyncSession):
    """Workers with no events should not appear (no rows to derive from)."""
    result = await get_worker_status_query(session=db_session)
    assert result == []


@pytest.mark.asyncio
async def test_worker_status_mixed(db_session: AsyncSession):
    """Mixed workers should get correct per-worker status."""
    now = datetime.now(UTC)
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker-online@localhost",
            timestamp=now - timedelta(seconds=5),
        )
    )
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker-stale@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker-offline@localhost",
            timestamp=now - timedelta(seconds=5),
        )
    )
    await db_session.commit()

    result = await get_worker_status_query(session=db_session)
    statuses = {w["hostname"]: w["status"] for w in result}

    assert statuses["worker-online@localhost"] == "online"
    assert statuses["worker-stale@localhost"] == "offline"
    assert statuses["worker-offline@localhost"] == "offline"


@pytest.mark.asyncio
async def test_task_chain_multiple_retries(db_session: AsyncSession):
    """Chain query should return the whole retry family ordered by time."""
    root_id = uuid.uuid4()
    retry_1 = uuid.uuid4()
    retry_2 = uuid.uuid4()
    now = datetime.now(UTC)

    for tid, parent, ts_off in [
        (root_id, None, 0),
        (retry_1, root_id, 10),
        (retry_2, retry_1, 20),
    ]:
        db_session.add(
            TaskEvent(
                event_type="started",
                task_id=tid,
                timestamp=now + timedelta(seconds=ts_off),
                hostname="worker1@localhost",
                root_id=root_id,
                parent_id=parent,
            )
        )
    await db_session.commit()

    result = await get_task_chain_query(str(retry_2), session=db_session)

    assert result["root_id"] == str(root_id)
    chain = result["chain"]
    assert len(chain) == 3
    # Ordered chronologically: original first, retry_2 last
    assert [node["task_id"] for node in chain] == [str(root_id), str(retry_1), str(retry_2)]
    assert chain[0]["parent_id"] is None
    assert chain[1]["parent_id"] == str(root_id)
    assert chain[2]["parent_id"] == str(retry_1)


@pytest.mark.asyncio
async def test_task_chain_single_task(db_session: AsyncSession):
    """A task with no retries should produce a chain of one."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    result = await get_task_chain_query(str(task_id), session=db_session)

    assert result["root_id"] == str(task_id)
    assert len(result["chain"]) == 1
    assert result["chain"][0]["task_id"] == str(task_id)


@pytest.mark.asyncio
async def test_task_chain_invalid_uuid(db_session: AsyncSession):
    """Invalid UUID should return an error."""
    result = await get_task_chain_query("not-a-uuid", session=db_session)
    assert "error" in result
