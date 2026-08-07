"""Tests for database models."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from taskowl.models import Task, Worker


@pytest.mark.asyncio
async def test_create_task(db_session):
    """Test creating a task."""
    task = Task(
        id=uuid.uuid4(),
        name="test_task",
        state="PENDING",
        args={"arg1": "value1"},
        kwargs={"kwarg1": "value2"},
        queue="default",
    )
    db_session.add(task)
    await db_session.commit()

    # Query the task
    result = await db_session.execute(select(Task).where(Task.id == task.id))
    retrieved_task = result.scalar_one()

    assert retrieved_task.name == "test_task"
    assert retrieved_task.state == "PENDING"
    assert retrieved_task.args == {"arg1": "value1"}
    assert retrieved_task.kwargs == {"kwarg1": "value2"}
    assert retrieved_task.queue == "default"
    assert retrieved_task.created_at is not None


@pytest.mark.asyncio
async def test_create_worker(db_session):
    """Test creating a worker."""
    worker = Worker(
        hostname="worker1@localhost",
        status="online",
        pool_size=4,
        active_count=2,
        processed_count=100,
        loadavg=[1.5, 2.0, 1.8],
    )
    db_session.add(worker)
    await db_session.commit()

    # Query the worker
    result = await db_session.execute(select(Worker).where(Worker.hostname == worker.hostname))
    retrieved_worker = result.scalar_one()

    assert retrieved_worker.hostname == "worker1@localhost"
    assert retrieved_worker.status == "online"
    assert retrieved_worker.pool_size == 4
    assert retrieved_worker.active_count == 2
    assert retrieved_worker.processed_count == 100
    assert retrieved_worker.loadavg == [1.5, 2.0, 1.8]


@pytest.mark.asyncio
async def test_task_state_transitions(db_session):
    """Test task state transitions."""
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        name="test_task",
        state="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    # Update to STARTED
    task.state = "STARTED"
    task.started_at = datetime.now(UTC)
    await db_session.commit()

    result = await db_session.execute(select(Task).where(Task.id == task_id))
    updated_task = result.scalar_one()
    assert updated_task.state == "STARTED"
    assert updated_task.started_at is not None

    # Update to SUCCESS
    task.state = "SUCCESS"
    task.finished_at = datetime.now(UTC)
    task.runtime = 1.5
    await db_session.commit()

    result = await db_session.execute(select(Task).where(Task.id == task_id))
    final_task = result.scalar_one()
    assert final_task.state == "SUCCESS"
    assert final_task.finished_at is not None
    assert final_task.runtime == 1.5
