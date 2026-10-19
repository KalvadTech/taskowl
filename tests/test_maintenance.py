"""Tests for retention/pruning maintenance."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.maintenance import prune_events
from taskowl.models import AutomationRun, TaskEvent, WorkerEvent


def _task_event(when: datetime, name: str = "test_task") -> TaskEvent:
    """Build a task event at the given time."""
    return TaskEvent(event_type="received", task_id=uuid.uuid4(), timestamp=when, name=name)


def _worker_event(when: datetime, hostname: str = "worker1@localhost") -> WorkerEvent:
    """Build a worker event at the given time."""
    return WorkerEvent(event_type="heartbeat", hostname=hostname, timestamp=when)


def _automation_run(when: datetime, automation_id: int = 1) -> AutomationRun:
    """Build an automation run at the given time."""
    return AutomationRun(
        automation_id=automation_id,
        trigger="event",
        matched=True,
        conditions_passed=True,
        created_at=when,
    )


async def _count(session: AsyncSession, model: type) -> int:
    """Count all rows in the given table."""
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar() or 0)


@pytest.mark.asyncio
async def test_prune_disabled_keeps_everything(db_session: AsyncSession):
    """Retention of 0 keeps all rows regardless of age."""
    now = datetime.now(UTC)
    db_session.add(_task_event(now - timedelta(days=365)))
    db_session.add(_worker_event(now - timedelta(days=365)))
    await db_session.commit()

    counts = await prune_events(
        db_session, now=now, event_retention_days=0, automation_run_retention_days=0
    )

    assert counts == {"task_events": 0, "worker_events": 0, "automation_runs": 0}
    assert await _count(db_session, TaskEvent) == 1
    assert await _count(db_session, WorkerEvent) == 1


@pytest.mark.asyncio
async def test_prune_deletes_old_keeps_new(db_session: AsyncSession):
    """Only events older than the retention window are deleted."""
    now = datetime.now(UTC)
    old = now - timedelta(days=10)
    recent = now - timedelta(hours=1)

    db_session.add(_task_event(old))
    db_session.add(_task_event(recent))
    db_session.add(_worker_event(old))
    db_session.add(_worker_event(recent))
    await db_session.commit()

    counts = await prune_events(
        db_session, now=now, event_retention_days=5, automation_run_retention_days=0
    )

    assert counts["task_events"] == 1
    assert counts["worker_events"] == 1
    assert await _count(db_session, TaskEvent) == 1
    assert await _count(db_session, WorkerEvent) == 1


@pytest.mark.asyncio
async def test_prune_dry_run_deletes_nothing(db_session: AsyncSession):
    """Dry-run reports the count without deleting anything."""
    now = datetime.now(UTC)
    db_session.add(_task_event(now - timedelta(days=10)))
    db_session.add(_task_event(now - timedelta(days=10)))
    await db_session.commit()

    counts = await prune_events(
        db_session,
        now=now,
        dry_run=True,
        event_retention_days=5,
        automation_run_retention_days=0,
    )

    assert counts["task_events"] == 2
    assert await _count(db_session, TaskEvent) == 2


@pytest.mark.asyncio
async def test_prune_loops_over_batches(db_session: AsyncSession):
    """A batch size smaller than the row count still deletes everything."""
    now = datetime.now(UTC)
    old = now - timedelta(days=10)
    for _ in range(5):
        db_session.add(_task_event(old))
    db_session.add(_task_event(now - timedelta(hours=1)))
    await db_session.commit()

    counts = await prune_events(
        db_session,
        now=now,
        batch_size=2,
        event_retention_days=5,
        automation_run_retention_days=0,
    )

    assert counts["task_events"] == 5
    assert await _count(db_session, TaskEvent) == 1


@pytest.mark.asyncio
async def test_prune_automation_runs_separately(db_session: AsyncSession):
    """Automation runs use their own retention window."""
    now = datetime.now(UTC)
    db_session.add(_automation_run(now - timedelta(days=10)))
    db_session.add(_automation_run(now - timedelta(hours=1)))
    # A very old task event must survive because event retention is disabled.
    db_session.add(_task_event(now - timedelta(days=10)))
    await db_session.commit()

    counts = await prune_events(
        db_session, now=now, event_retention_days=0, automation_run_retention_days=5
    )

    assert counts["automation_runs"] == 1
    assert counts["task_events"] == 0
    assert await _count(db_session, AutomationRun) == 1
    assert await _count(db_session, TaskEvent) == 1
