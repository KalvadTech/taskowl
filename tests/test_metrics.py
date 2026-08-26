"""Tests for the Prometheus metrics endpoint."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.metrics import generate_metrics
from taskowl.models import TaskEvent, WorkerEvent


@pytest.mark.asyncio
async def test_metrics_empty_db(db_session: AsyncSession):
    """Empty DB should produce valid Prometheus text with zero values."""
    body = await generate_metrics(db_session)
    text = body.decode()
    assert "taskowl_task_events_total" in text
    assert "taskowl_worker_status" in text
    assert "taskowl_task_execution_duration_seconds" in text
    # No errors, no lines after the header
    assert "taskowl_task_events_total 0.0" not in text  # no labels -> no sample


@pytest.mark.asyncio
async def test_metrics_task_events(db_session: AsyncSession):
    """Task events should be counted with correct labels."""
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now,
            hostname="worker1@localhost",
            name="myapp.tasks.process",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=uuid.uuid4(),
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
            name="myapp.tasks.process",
            runtime=1.5,
        )
    )
    await db_session.commit()

    text = (await generate_metrics(db_session)).decode()

    assert 'taskowl_task_events_total{event_type="received"' in text
    assert 'task_name="myapp.tasks.process"' in text
    assert 'worker="worker1@localhost"' in text
    # Histogram should have the observed runtime
    count_line = (
        'taskowl_task_execution_duration_seconds_count{task_name="myapp.tasks.process"} 1.0'
    )
    sum_line = 'taskowl_task_execution_duration_seconds_sum{task_name="myapp.tasks.process"} 1.5'
    assert count_line in text
    assert sum_line in text


@pytest.mark.asyncio
async def test_metrics_worker_status_online(db_session: AsyncSession):
    """A worker with a recent heartbeat should be online (1)."""
    now = datetime.now(UTC)
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="celery@w1",
            timestamp=now - timedelta(seconds=5),
            active=2,
            processed=10,
        )
    )
    await db_session.commit()

    text = (await generate_metrics(db_session)).decode()

    assert 'taskowl_worker_status{worker="celery@w1"} 1.0' in text
    assert 'taskowl_worker_active_tasks{worker="celery@w1"} 2.0' in text
    assert 'taskowl_worker_processed_total{worker="celery@w1"} 10.0' in text


@pytest.mark.asyncio
async def test_metrics_worker_status_offline(db_session: AsyncSession):
    """A worker with a stale heartbeat should be offline (0)."""
    now = datetime.now(UTC)
    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="celery@w2",
            timestamp=now - timedelta(seconds=300),
        )
    )
    await db_session.commit()

    text = (await generate_metrics(db_session)).decode()

    assert 'taskowl_worker_status{worker="celery@w2"} 0.0' in text


@pytest.mark.asyncio
async def test_api_metrics_endpoint(client: AsyncClient):
    """GET /metrics should return 200 with Prometheus content type."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "taskowl_task_events_total" in response.text


@pytest.mark.asyncio
async def test_api_metrics_no_auth(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Metrics endpoint should work without an API key."""
    response = await client.get("/metrics")
    assert response.status_code == 200
