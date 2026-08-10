"""Reusable query functions for taskowl.

These functions contain the core database query logic that can be used
by both REST API endpoints and MCP tools.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.database import async_session_maker
from taskowl.models import TaskEvent, WorkerEvent


async def list_tasks_query(
    state: str | None = None,
    name: str | None = None,
    worker: str | None = None,
    since: str | None = None,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> list[dict]:
    """List tasks with optional filters.

    Args:
        state: Filter by state (received, started, succeeded, failed, retried, revoked)
        name: Filter by task name
        worker: Filter by worker hostname
        since: Only tasks created after this datetime (ISO 8601)
        limit: Max number of tasks to return (default: 100)
        session: Optional database session (for testing)

    Returns:
        List of task dictionaries
    """
    if session is None:
        async with async_session_maker() as session:
            return await _list_tasks_impl(session, state, name, worker, since, limit)
    return await _list_tasks_impl(session, state, name, worker, since, limit)


async def _list_tasks_impl(
    session: AsyncSession,
    state: str | None,
    name: str | None,
    worker: str | None,
    since: str | None,
    limit: int,
) -> list[dict]:
    """Internal implementation of list_tasks_query."""
    # Get latest event per task using a subquery to find max timestamp per task
    # This approach works with both PostgreSQL and SQLite
    from sqlalchemy import func as sql_func

    # Subquery to get max timestamp per task
    max_timestamps = (
        select(
            TaskEvent.task_id,
            sql_func.max(TaskEvent.timestamp).label("max_ts"),
        )
        .group_by(TaskEvent.task_id)
        .subquery()
    )

    # Main query to get the full event records
    query = select(TaskEvent).join(
        max_timestamps,
        (TaskEvent.task_id == max_timestamps.c.task_id)
        & (TaskEvent.timestamp == max_timestamps.c.max_ts),
    )

    # Apply filters
    if state:
        query = query.where(TaskEvent.event_type == state.lower())
    if name:
        query = query.where(TaskEvent.name == name)
    if worker:
        query = query.where(TaskEvent.hostname == worker)
    if since:
        since_dt = datetime.fromisoformat(since)
        query = query.where(TaskEvent.timestamp >= since_dt)

    # Apply limit
    query = query.limit(limit)

    result = await session.execute(query)
    events = result.scalars().all()

    # Format response
    task_list = []
    for event in events:
        task_list.append(
            {
                "id": str(event.task_id),
                "name": event.name,
                "state": event.event_type,
                "worker": event.hostname,
                "queue": event.queue,
                "timestamp": event.timestamp.isoformat(),
            }
        )

    return task_list


async def get_task_query(task_id: str, session: AsyncSession | None = None) -> dict:
    """Get detailed information about a specific task.

    Args:
        task_id: UUID of the task
        session: Optional database session (for testing)

    Returns:
        Task dictionary with all events
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return {"error": f"Invalid task_id format: {task_id}"}

    if session is None:
        async with async_session_maker() as session:
            return await _get_task_impl(session, task_uuid, task_id)
    return await _get_task_impl(session, task_uuid, task_id)


async def _get_task_impl(session: AsyncSession, task_uuid: uuid.UUID, task_id: str) -> dict:
    """Internal implementation of get_task_query."""
    # Get all events for this task, ordered by timestamp
    query = select(TaskEvent).where(TaskEvent.task_id == task_uuid).order_by(TaskEvent.timestamp)
    result = await session.execute(query)
    events = result.scalars().all()

    if not events:
        return {"error": f"Task not found: {task_id}"}

    # Reconstruct task state from events
    task_state: dict = {
        "id": str(task_uuid),
        "events": [],
    }

    for event in events:
        event_data = {
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "hostname": event.hostname,
        }

        # Add event-specific fields
        if event.name:
            task_state["name"] = event.name
        if event.args:
            task_state["args"] = event.args
        if event.kwargs:
            task_state["kwargs"] = event.kwargs
        if event.result:
            task_state["result"] = event.result
        if event.exception:
            task_state["exception"] = event.exception
        if event.traceback:
            task_state["traceback"] = event.traceback
        if event.runtime is not None:
            task_state["runtime"] = event.runtime
        if event.queue:
            task_state["queue"] = event.queue

        task_state["events"].append(event_data)

    # Set current state from last event
    task_state["state"] = events[-1].event_type
    task_state["worker"] = events[-1].hostname

    return task_state


async def get_task_timeline_query(task_id: str, session: AsyncSession | None = None) -> list[dict]:
    """Get all events for a task in chronological order.

    Args:
        task_id: UUID of the task
        session: Optional database session (for testing)

    Returns:
        List of timeline entries
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return [{"error": f"Invalid task_id format: {task_id}"}]

    if session is None:
        async with async_session_maker() as session:
            return await _get_task_timeline_impl(session, task_uuid, task_id)
    return await _get_task_timeline_impl(session, task_uuid, task_id)


async def _get_task_timeline_impl(
    session: AsyncSession, task_uuid: uuid.UUID, task_id: str
) -> list[dict]:
    """Internal implementation of get_task_timeline_query."""
    query = (
        select(TaskEvent).where(TaskEvent.task_id == task_uuid).order_by(TaskEvent.timestamp.asc())
    )
    result = await session.execute(query)
    events = result.scalars().all()

    if not events:
        return [{"error": f"Task not found: {task_id}"}]

    timeline = []
    for event in events:
        timeline_entry = {
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "hostname": event.hostname,
        }

        # Add relevant details based on event type
        details = {}
        if event.name:
            details["name"] = event.name
        if event.runtime is not None:
            details["runtime"] = event.runtime
        if event.exception:
            details["exception"] = event.exception
        if event.result:
            details["result"] = event.result
        if event.retries is not None:
            details["retries"] = event.retries
        if event.pid is not None:
            details["pid"] = event.pid
        if event.terminated is not None:
            details["terminated"] = event.terminated
        if event.expired is not None:
            details["expired"] = event.expired

        if details:
            timeline_entry["details"] = details

        timeline.append(timeline_entry)

    return timeline


async def get_task_summary_query(hours: int = 1, session: AsyncSession | None = None) -> dict:
    """Get aggregate task statistics.

    Args:
        hours: Time window in hours (default: 1)
        session: Optional database session (for testing)

    Returns:
        Summary dictionary with statistics
    """
    since = datetime.now(UTC) - timedelta(hours=hours)

    if session is None:
        async with async_session_maker() as session:
            return await _get_task_summary_impl(session, since, hours)
    return await _get_task_summary_impl(session, since, hours)


async def _get_task_summary_impl(session: AsyncSession, since: datetime, hours: int) -> dict:
    """Internal implementation of get_task_summary_query."""
    from sqlalchemy import func as sql_func

    # Get latest event per task within time window using subquery approach
    # This works with both PostgreSQL and SQLite

    # First, get all task_ids that have events in the time window
    task_ids_in_window = (
        select(TaskEvent.task_id).where(TaskEvent.timestamp >= since).distinct().subquery()
    )

    # Get max timestamp per task within the time window
    max_timestamps = (
        select(
            TaskEvent.task_id,
            sql_func.max(TaskEvent.timestamp).label("max_ts"),
        )
        .where(TaskEvent.task_id.in_(select(task_ids_in_window.c.task_id)))
        .group_by(TaskEvent.task_id)
        .subquery()
    )

    # Get the full event records for the latest events
    latest_events = (
        select(TaskEvent)
        .join(
            max_timestamps,
            (TaskEvent.task_id == max_timestamps.c.task_id)
            & (TaskEvent.timestamp == max_timestamps.c.max_ts),
        )
        .subquery()
    )

    # Count by event_type (state)
    query = select(latest_events.c.event_type, func.count()).group_by(latest_events.c.event_type)
    result = await session.execute(query)
    state_counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

    # Calculate average runtime for succeeded tasks
    query = select(func.avg(TaskEvent.runtime)).where(
        and_(
            TaskEvent.event_type == "succeeded",
            TaskEvent.timestamp >= since,
            TaskEvent.runtime.isnot(None),
        )
    )
    result = await session.execute(query)
    avg_runtime = result.scalar()

    return {
        "period_hours": hours,
        "total_tasks": sum(state_counts.values()),
        "by_state": state_counts,
        "avg_runtime_seconds": round(avg_runtime, 2) if avg_runtime else None,
    }


async def get_worker_status_query(session: AsyncSession | None = None) -> list[dict]:
    """Get status of all Celery workers.

    Args:
        session: Optional database session (for testing)

    Returns:
        List of worker dictionaries
    """
    if session is None:
        async with async_session_maker() as session:
            return await _get_worker_status_impl(session)
    return await _get_worker_status_impl(session)


async def _get_worker_status_impl(session: AsyncSession) -> list[dict]:
    """Internal implementation of get_worker_status_query."""
    # Get latest event per worker using a subquery to find max timestamp per worker
    # This approach works with both PostgreSQL and SQLite
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

    # Main query to get the full event records
    query = select(WorkerEvent).join(
        max_timestamps,
        (WorkerEvent.hostname == max_timestamps.c.hostname)
        & (WorkerEvent.timestamp == max_timestamps.c.max_ts),
    )

    result = await session.execute(query)
    events = result.scalars().all()

    worker_list = []
    for event in events:
        worker_info = {
            "hostname": event.hostname,
            "status": event.event_type,
            "last_heartbeat": event.timestamp.isoformat(),
        }

        # Add heartbeat-specific fields if available
        if event.active is not None:
            worker_info["active"] = event.active
        if event.processed is not None:
            worker_info["processed"] = event.processed
        if event.freq is not None:
            worker_info["freq"] = event.freq
        if event.sw_ident:
            worker_info["sw_ident"] = event.sw_ident
        if event.sw_ver:
            worker_info["sw_ver"] = event.sw_ver
        if event.sw_sys:
            worker_info["sw_sys"] = event.sw_sys

        worker_list.append(worker_info)

    return worker_list
