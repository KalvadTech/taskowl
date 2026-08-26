"""Prometheus metrics for taskowl.

Exposes task and worker telemetry in the Prometheus text format. Metrics are
computed on-scrape by querying the append-only event tables (task_events,
worker_events), so there is no accumulated in-memory state and results always
reflect the current database contents.
"""

from datetime import UTC, datetime, timedelta

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.models import TaskEvent, WorkerEvent

# NOTE: The /metrics endpoint is intentionally UNAUTHENTICATED so that
# Prometheus can scrape it without sending the taskowl API key. Ensure this
# endpoint is only reachable from trusted networks / behind a reverse proxy.
# TODO: consider placing /metrics behind network-level auth or a separate
# scraper token if it is exposed beyond a trusted network.


async def generate_metrics(session: AsyncSession) -> bytes:
    """Generate Prometheus metrics text by querying the event tables."""
    registry = CollectorRegistry()

    task_events_total = Counter(
        "taskowl_task_events_total",
        "Number of task events observed",
        ["event_type", "task_name", "worker"],
        registry=registry,
    )
    task_duration = Histogram(
        "taskowl_task_execution_duration_seconds",
        "Task execution duration",
        ["task_name"],
        registry=registry,
    )
    worker_status = Gauge(
        "taskowl_worker_status",
        "Worker availability (1 = online, 0 = offline)",
        ["worker"],
        registry=registry,
    )
    worker_active_tasks = Gauge(
        "taskowl_worker_active_tasks",
        "Number of tasks currently being processed by a worker",
        ["worker"],
        registry=registry,
    )
    worker_processed_total = Counter(
        "taskowl_worker_processed_total",
        "Total number of tasks processed by a worker",
        ["worker"],
        registry=registry,
    )

    await _populate_task_metrics(session, task_events_total, task_duration)
    await _populate_worker_metrics(
        session, worker_status, worker_active_tasks, worker_processed_total
    )

    return generate_latest(registry)


async def _populate_task_metrics(
    session: AsyncSession,
    task_events_total: Counter,
    task_duration: Histogram,
) -> None:
    """Populate task event counts and execution duration histogram."""
    # Event counts grouped by event type, task name, and worker
    result = await session.execute(
        select(
            TaskEvent.event_type,
            func.coalesce(TaskEvent.name, ""),
            func.coalesce(TaskEvent.hostname, ""),
            func.count(),
        ).group_by(TaskEvent.event_type, TaskEvent.name, TaskEvent.hostname)
    )
    for event_type, task_name, worker, count in result.all():
        task_events_total.labels(event_type, task_name, worker).inc(count)

    # Execution duration histogram from succeeded events with runtime
    result = await session.execute(
        select(
            func.coalesce(TaskEvent.name, ""),
            TaskEvent.runtime,
        ).where(
            TaskEvent.event_type == "succeeded",
            TaskEvent.runtime.isnot(None),
        )
    )
    for task_name, runtime in result.all():
        task_duration.labels(task_name).observe(runtime)


async def _populate_worker_metrics(
    session: AsyncSession,
    worker_status: Gauge,
    worker_active_tasks: Gauge,
    worker_processed_total: Counter,
) -> None:
    """Populate worker status, active tasks, and processed totals.

    Uses the latest event per worker to derive status (online/offline based on
    the offline timeout) and heartbeat fields.
    """
    from sqlalchemy import func as sql_func

    # Subquery to get max timestamp per worker
    max_timestamps = (
        select(
            WorkerEvent.hostname,
            sql_func.max(WorkerEvent.timestamp).label("max_ts"),
        )
        .group_by(WorkerEvent.hostname)
        .subquery()
    )

    query = select(WorkerEvent).join(
        max_timestamps,
        (WorkerEvent.hostname == max_timestamps.c.hostname)
        & (WorkerEvent.timestamp == max_timestamps.c.max_ts),
    )
    result = await session.execute(query)
    events = result.scalars().all()

    now = datetime.now(UTC)
    offline_timeout = timedelta(seconds=30)

    for event in events:
        hostname = event.hostname
        status = _is_online(event, now, offline_timeout)
        worker_status.labels(hostname).set(1 if status else 0)

        if event.active is not None:
            worker_active_tasks.labels(hostname).set(event.active)
        if event.processed is not None:
            worker_processed_total.labels(hostname).inc(event.processed)


def _is_online(event: WorkerEvent, now: datetime, offline_timeout: timedelta) -> bool:
    """Determine whether a worker is online based on its latest event."""
    if event.event_type == "offline":
        return False
    # Normalize timezone (SQLite returns naive datetimes)
    ts = event.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return now - ts <= offline_timeout
