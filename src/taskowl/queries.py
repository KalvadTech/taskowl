"""Reusable query functions for taskowl.

These functions contain the core database query logic that can be used
by both REST API endpoints and MCP tools.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.config import settings
from taskowl.database import async_session_maker
from taskowl.models import TaskEvent, WorkerEvent


async def list_tasks_query(
    state: str | None = None,
    name: str | None = None,
    worker: str | None = None,
    since: str | None = None,
    limit: int = 100,
    search: str | None = None,
    offset: int = 0,
    sort_by: str = "timestamp",
    session: AsyncSession | None = None,
) -> list[dict] | dict:
    """List tasks with optional filters.

    Args:
        state: Filter by state (received, started, succeeded, failed, retried, revoked)
        name: Filter by exact task name
        worker: Filter by worker hostname
        since: Only tasks created after this datetime (ISO 8601)
        limit: Max number of tasks to return (default: 100)
        search: Partial, case-insensitive match on task name
        offset: Number of tasks to skip (for pagination)
        sort_by: Sort key (timestamp, name, state, worker). Defaults to timestamp, newest first
        session: Optional database session (for testing)

    Returns:
        List of task dictionaries
    """
    if session is None:
        async with async_session_maker() as session:
            return await _list_tasks_impl(
                session, state, name, worker, since, limit, search, offset, sort_by
            )
    return await _list_tasks_impl(
        session, state, name, worker, since, limit, search, offset, sort_by
    )


async def _list_tasks_impl(
    session: AsyncSession,
    state: str | None,
    name: str | None,
    worker: str | None,
    since: str | None,
    limit: int,
    search: str | None,
    offset: int,
    sort_by: str,
) -> list[dict] | dict:
    """Internal implementation of list_tasks_query."""
    # This approach works with both PostgreSQL and SQLite
    from sqlalchemy import func as sql_func

    # Subquery to get max timestamp per task (latest event)
    max_timestamps = (
        select(
            TaskEvent.task_id,
            sql_func.max(TaskEvent.timestamp).label("max_ts"),
        )
        .group_by(TaskEvent.task_id)
        .subquery()
    )

    # Subquery to get the earliest event that carries a name, per task
    earliest_named_ts = (
        select(
            TaskEvent.task_id,
            sql_func.min(TaskEvent.timestamp).label("name_ts"),
        )
        .where(TaskEvent.name.isnot(None))
        .group_by(TaskEvent.task_id)
        .subquery()
    )
    task_names = (
        select(TaskEvent.task_id, TaskEvent.name)
        .join(
            earliest_named_ts,
            (TaskEvent.task_id == earliest_named_ts.c.task_id)
            & (TaskEvent.timestamp == earliest_named_ts.c.name_ts),
        )
        .subquery()
    )

    # Main query to get the full event records
    query = (
        select(TaskEvent, task_names.c.name.label("task_name"))
        .join(
            max_timestamps,
            (TaskEvent.task_id == max_timestamps.c.task_id)
            & (TaskEvent.timestamp == max_timestamps.c.max_ts),
        )
        .join(
            task_names,
            TaskEvent.task_id == task_names.c.task_id,
            isouter=True,
        )
    )

    # Apply filters
    if state:
        query = query.where(TaskEvent.event_type == state.lower())
    if name:
        query = query.where(task_names.c.name == name)
    if search:
        query = query.where(task_names.c.name.ilike(f"%{search}%"))
    if worker:
        query = query.where(TaskEvent.hostname == worker)
    if since:
        since_dt = datetime.fromisoformat(since)
        query = query.where(TaskEvent.timestamp >= since_dt)

    # Apply ordering
    sort_keys = {
        "timestamp": TaskEvent.timestamp,
        "name": task_names.c.name,
        "state": TaskEvent.event_type,
        "worker": TaskEvent.hostname,
    }
    if sort_by not in sort_keys:
        return {"error": f"Invalid sort_by: {sort_by}. Must be one of {list(sort_keys)}"}
    column = sort_keys[sort_by]
    if sort_by == "timestamp":
        # Newest first by default
        query = query.order_by(column.desc())
    else:
        query = query.order_by(column.asc())

    # Apply limit/offset
    offset = max(offset, 0)
    query = query.offset(offset).limit(limit)

    result = await session.execute(query)
    rows = result.all()

    # Format response
    task_list = []
    for event, task_name in rows:
        task_list.append(
            {
                "id": str(event.task_id),
                "name": task_name,
                "state": event.event_type,
                "worker": event.hostname,
                "queue": event.queue,
                "timestamp": event.timestamp.isoformat(),
            }
        )

    return task_list


async def list_task_types_query(
    limit: int = 50,
    session: AsyncSession | None = None,
) -> list[dict]:
    """List distinct task names (types) with their task counts.

    Args:
        limit: Max number of task types to return (default: 50)
        session: Optional database session (for testing)

    Returns:
        List of dicts with name and count, ordered by count descending
    """
    if session is None:
        async with async_session_maker() as session:
            return await _list_task_types_impl(session, limit)
    return await _list_task_types_impl(session, limit)


async def _list_task_types_impl(session: AsyncSession, limit: int) -> list[dict]:
    """Internal implementation of list_task_types_query."""
    from sqlalchemy import func as sql_func

    # Task name is only present on the earliest named event per task
    earliest_named_ts = (
        select(
            TaskEvent.task_id,
            sql_func.min(TaskEvent.timestamp).label("name_ts"),
        )
        .where(TaskEvent.name.isnot(None))
        .group_by(TaskEvent.task_id)
        .subquery()
    )
    task_names = (
        select(TaskEvent.task_id, TaskEvent.name)
        .join(
            earliest_named_ts,
            (TaskEvent.task_id == earliest_named_ts.c.task_id)
            & (TaskEvent.timestamp == earliest_named_ts.c.name_ts),
        )
        .subquery()
    )

    query = (
        select(task_names.c.name, sql_func.count().label("count"))
        .group_by(task_names.c.name)
        .order_by(sql_func.count().desc(), task_names.c.name.asc())
        .limit(limit)
    )
    result = await session.execute(query)
    return [{"name": row[0], "count": row[1]} for row in result.all()]


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
        "root_id": None,
        "parent_id": None,
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
        if event.root_id:
            task_state["root_id"] = str(event.root_id)
        if event.parent_id:
            task_state["parent_id"] = str(event.parent_id)

        task_state["events"].append(event_data)

    # Set current state from last event
    task_state["state"] = events[-1].event_type
    task_state["worker"] = events[-1].hostname

    # Compute orphan status (query-time detection)
    task_state["orphaned"] = await _task_is_orphaned_impl(
        session, task_uuid, events[-1], datetime.now(UTC)
    )

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

    now = datetime.now(UTC)
    worker_list = []
    for event in events:
        worker_info = {
            "hostname": event.hostname,
            "status": _worker_status(event, now),
            "last_event": event.event_type,
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


def _worker_status(event: WorkerEvent, now: datetime) -> str:
    """Derive a worker's status from its latest event and the offline timeout.

    Returns:
        "offline" if the latest event is an offline event or the last
        heartbeat is stale, "online" if the worker has a recent heartbeat,
        or "unknown" if there is no event data.
    """
    timeout = timedelta(seconds=settings.worker_offline_timeout_seconds)

    if event.event_type == "offline":
        return "offline"
    # Normalize timezone (SQLite returns naive datetimes)
    event_ts = _ensure_utc(event.timestamp)
    if now - event_ts > timeout:
        # Stale heartbeat/online -> worker presumed dead
        return "offline"
    return "online"


async def _worker_is_offline(
    session: AsyncSession,
    hostname: str,
    now: datetime,
    offline_timeout: timedelta,
) -> bool:
    """Determine whether a worker is offline based on its latest event."""
    query = (
        select(WorkerEvent)
        .where(WorkerEvent.hostname == hostname)
        .order_by(WorkerEvent.timestamp.desc())
        .limit(1)
    )
    result = await session.execute(query)
    event = result.scalar_one_or_none()

    if event is None:
        # No worker events at all -> assume offline
        return True
    if event.event_type == "offline":
        return True
    # Normalize timezone (SQLite returns naive datetimes)
    event_ts = _ensure_utc(event.timestamp)
    # Stale heartbeat/online -> worker presumed dead
    return now - event_ts > offline_timeout


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def _task_is_orphaned_impl(
    session: AsyncSession,
    task_uuid: uuid.UUID,
    latest_event: TaskEvent,
    now: datetime,
) -> bool:
    """Check whether a task is orphaned given its latest event."""
    grace = timedelta(seconds=settings.orphan_grace_seconds)
    offline_timeout = timedelta(seconds=settings.worker_offline_timeout_seconds)

    # Rule 1: latest event must be 'started'
    if latest_event.event_type != "started":
        return False

    # Rule 2: started must be older than the grace period
    # Normalize timezone (SQLite returns naive datetimes)
    event_ts = _ensure_utc(latest_event.timestamp)
    if now - event_ts <= grace:
        return False

    # Rule 3: the worker must be offline
    if not latest_event.hostname:
        return False
    return await _worker_is_offline(session, latest_event.hostname, now, offline_timeout)


async def list_orphaned_tasks_query(
    limit: int = 100,
    session: AsyncSession | None = None,
) -> list[dict]:
    """List tasks currently considered orphaned.

    A task is orphaned when it is stuck in STARTED state and its worker went
    offline (crashed / network drop) before sending a completion event.

    Args:
        limit: Max number of tasks to return (default: 100)
        session: Optional database session (for testing)

    Returns:
        List of orphaned task dictionaries
    """
    if session is None:
        async with async_session_maker() as session:
            return await _list_orphaned_tasks_impl(session, limit)
    return await _list_orphaned_tasks_impl(session, limit)


async def _list_orphaned_tasks_impl(session: AsyncSession, limit: int) -> list[dict]:
    """Internal implementation of list_orphaned_tasks_query."""
    from sqlalchemy import func as sql_func

    now = datetime.now(UTC)

    # Subquery to get max timestamp per task
    max_timestamps = (
        select(
            TaskEvent.task_id,
            sql_func.max(TaskEvent.timestamp).label("max_ts"),
        )
        .group_by(TaskEvent.task_id)
        .subquery()
    )

    # Get the latest event per task
    latest_events_query = select(TaskEvent).join(
        max_timestamps,
        (TaskEvent.task_id == max_timestamps.c.task_id)
        & (TaskEvent.timestamp == max_timestamps.c.max_ts),
    )
    result = await session.execute(latest_events_query)
    latest_events = result.scalars().all()

    orphaned_tasks = []
    for event in latest_events:
        if await _task_is_orphaned_impl(session, event.task_id, event, now):
            orphaned_tasks.append(
                {
                    "id": str(event.task_id),
                    "name": event.name,
                    "state": "orphaned",
                    "worker": event.hostname,
                    "queue": event.queue,
                    "started_at": event.timestamp.isoformat(),
                }
            )

    # Reconstruct the task name from the earliest named event (the latest
    # event of an orphan is 'started', which does not carry the name)
    if orphaned_tasks:
        task_ids = [t["id"] for t in orphaned_tasks if t["id"] is not None]
        names = await _task_names_map(session, task_ids)
        for task in orphaned_tasks:
            task["name"] = names.get(task["id"])

    return orphaned_tasks[:limit]


async def _task_names_map(session: AsyncSession, task_ids: list[str]) -> dict[str, str | None]:
    """Return {task_id: name} using each task's earliest named event.

    The task name is only present on 'sent'/'received' events, so the latest
    event (e.g. 'succeeded', 'started') usually does not carry it. This maps
    each task id to the name found on its earliest event that has one.
    """
    from sqlalchemy import func as sql_func

    earliest_named_ts = (
        select(
            TaskEvent.task_id,
            sql_func.min(TaskEvent.timestamp).label("name_ts"),
        )
        .where(
            TaskEvent.task_id.in_([uuid.UUID(t) for t in task_ids]),
            TaskEvent.name.isnot(None),
        )
        .group_by(TaskEvent.task_id)
        .subquery()
    )
    query = select(TaskEvent.task_id, TaskEvent.name).join(
        earliest_named_ts,
        (TaskEvent.task_id == earliest_named_ts.c.task_id)
        & (TaskEvent.timestamp == earliest_named_ts.c.name_ts),
    )
    result = await session.execute(query)
    return {str(task_id): name for task_id, name in result.all()}


async def get_task_chain_query(task_id: str, session: AsyncSession | None = None) -> dict:
    """Get the full retry chain for a task, ordered chronologically.

    The chain includes every task that shares the root task id (the original
    task and all of its retries). Each node exposes its current state plus
    parent linkage so branching (if any) remains visible.

    Args:
        task_id: UUID of the task
        session: Optional database session (for testing)

    Returns:
        Dict with root_id and an ordered chain list
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return {"error": f"Invalid task_id format: {task_id}"}

    if session is None:
        async with async_session_maker() as session:
            return await _get_task_chain_impl(session, task_uuid, task_id)
    return await _get_task_chain_impl(session, task_uuid, task_id)


async def _get_task_chain_impl(session: AsyncSession, task_uuid: uuid.UUID, task_id: str) -> dict:
    """Internal implementation of get_task_chain_query."""
    # Resolve the root id for this task
    root_query = (
        select(TaskEvent.root_id)
        .where(TaskEvent.task_id == task_uuid, TaskEvent.root_id.isnot(None))
        .order_by(TaskEvent.timestamp.desc())
        .limit(1)
    )
    root_result = await session.execute(root_query)
    root_id = root_result.scalar_one_or_none()

    if root_id is None:
        # No root recorded; the task is its own chain (or we can't find it)
        root_id = task_uuid

    # Find all tasks in the retry family sharing this root,
    # always including the queried task itself (even if it has no root_id)
    family = (
        select(
            TaskEvent.task_id,
            func.min(TaskEvent.timestamp).label("first_ts"),
        )
        .where((TaskEvent.root_id == root_id) | (TaskEvent.task_id == task_uuid))
        .group_by(TaskEvent.task_id)
        .subquery()
    )

    # Get the latest event per task in the family
    max_timestamps = (
        select(
            TaskEvent.task_id,
            func.max(TaskEvent.timestamp).label("max_ts"),
        )
        .where(TaskEvent.task_id.in_(select(family.c.task_id)))
        .group_by(TaskEvent.task_id)
        .subquery()
    )
    latest_events_query = select(TaskEvent).join(
        max_timestamps,
        (TaskEvent.task_id == max_timestamps.c.task_id)
        & (TaskEvent.timestamp == max_timestamps.c.max_ts),
    )
    result = await session.execute(latest_events_query)
    latest_events = result.scalars().all()

    # Build the chain nodes
    chain_map: dict[uuid.UUID, dict] = {}
    for event in latest_events:
        chain_map[event.task_id] = {
            "task_id": str(event.task_id),
            "parent_id": str(event.parent_id) if event.parent_id else None,
            "state": event.event_type,
            "started_at": event.timestamp.isoformat(),
            "runtime": event.runtime,
        }

    # Order by the first event timestamp in the family
    result = await session.execute(
        select(family.c.task_id, family.c.first_ts).order_by(family.c.first_ts)
    )
    ordered_ids = [row[0] for row in result.all()]

    chain = [chain_map[tid] for tid in ordered_ids if tid in chain_map]

    return {"root_id": str(root_id), "chain": chain}
