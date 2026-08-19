"""Task action functions for taskowl.

This module contains the core logic for task write operations
(retry, revoke/cancel) that can be used by both REST API and MCP tools.
"""

import uuid

from celery import Celery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.config import settings
from taskowl.database import async_session_maker
from taskowl.models import TaskEvent


def _get_celery_app() -> Celery:
    """Get Celery app instance configured with broker URL."""
    return Celery(broker=settings.celery_broker_url)


async def _task_exists(session: AsyncSession, task_uuid: uuid.UUID) -> bool:
    """Check if a task exists in the database."""
    query = select(TaskEvent).where(TaskEvent.task_id == task_uuid).limit(1)
    result = await session.execute(query)
    return result.scalar_one_or_none() is not None


async def _get_task_info(session: AsyncSession, task_uuid: uuid.UUID) -> dict | None:
    """Get task information for retry."""
    # Get all events for this task
    query = select(TaskEvent).where(TaskEvent.task_id == task_uuid).order_by(TaskEvent.timestamp)
    result = await session.execute(query)
    events = result.scalars().all()

    if not events:
        return None

    # Reconstruct task info from events
    task_info: dict = {
        "state": events[-1].event_type,
        "name": None,
        "args": None,
        "kwargs": None,
        "queue": None,
    }

    for event in events:
        if event.name:
            task_info["name"] = event.name
        if event.args:
            task_info["args"] = event.args
        if event.kwargs:
            task_info["kwargs"] = event.kwargs
        if event.queue:
            task_info["queue"] = event.queue

    return task_info


async def revoke_task(
    task_id: str,
    terminate: bool = False,
    session: AsyncSession | None = None,
) -> dict:
    """Revoke (cancel) a task.

    Args:
        task_id: UUID of the task to revoke
        terminate: If True, terminate the task if it's currently running
        session: Optional database session (for testing)

    Returns:
        Dict with status and message
    """
    # Validate task_id format
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return {"error": f"Invalid task_id format: {task_id}"}

    # Check if task exists in our database
    if session is None:
        async with async_session_maker() as db_session:
            exists = await _task_exists(db_session, task_uuid)
    else:
        exists = await _task_exists(session, task_uuid)

    if not exists:
        return {"error": f"Task not found: {task_id}"}

    # Send revoke command to Celery
    try:
        app = _get_celery_app()
        app.control.revoke(task_id, terminate=terminate)
        return {
            "status": "success",
            "message": f"Task {task_id} has been revoked",
            "terminated": terminate,
        }
    except Exception as e:
        return {"error": f"Failed to revoke task: {str(e)}"}


async def retry_task(
    task_id: str,
    session: AsyncSession | None = None,
) -> dict:
    """Retry a failed/revoked task by creating a new task with same parameters.

    Args:
        task_id: UUID of the task to retry
        session: Optional database session (for testing)

    Returns:
        Dict with status, message, and new_task_id
    """
    # Validate task_id format
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return {"error": f"Invalid task_id format: {task_id}"}

    # Get original task details from database
    if session is None:
        async with async_session_maker() as db_session:
            task_info = await _get_task_info(db_session, task_uuid)
    else:
        task_info = await _get_task_info(session, task_uuid)

    if task_info is None:
        return {"error": f"Task not found: {task_id}"}

    # Check if task is in a retryable state
    if task_info["state"] not in ["failed", "revoked"]:
        return {
            "error": (
                f"Task is in '{task_info['state']}' state. "
                "Only failed or revoked tasks can be retried."
            )
        }

    # Check if we have the task name (required for retry)
    if not task_info["name"]:
        return {"error": "Cannot retry task: task name not found in events"}

    # Send new task to Celery
    try:
        app = _get_celery_app()
        result = app.send_task(
            task_info["name"],
            args=task_info.get("args"),
            kwargs=task_info.get("kwargs"),
            queue=task_info.get("queue"),
        )
        return {
            "status": "success",
            "message": f"Task {task_id} has been retried",
            "new_task_id": result.id,
        }
    except Exception as e:
        return {"error": f"Failed to retry task: {str(e)}"}
