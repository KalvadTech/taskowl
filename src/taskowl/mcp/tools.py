"""MCP tools for taskowl.

This module defines the MCP tools that can be used by LLMs to query
task and worker information.
"""

import uuid
from datetime import UTC, datetime, timedelta

from mcp.server import MCPServer

from taskowl.database import async_session_maker
from taskowl.models import Task, Worker


def register_tools(server: MCPServer) -> None:
    """Register all MCP tools with the server."""

    @server.tool(
        name="list_tasks",
        description="List tasks with optional filters",
    )
    async def list_tasks(
        state: str | None = None,
        name: str | None = None,
        worker: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List tasks with optional filters.

        Args:
            state: Filter by state (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED)
            name: Filter by task name
            worker: Filter by worker hostname
            since: Only tasks created after this datetime (ISO 8601)
            limit: Max number of tasks to return (default: 100)
        """
        from sqlalchemy import select

        async with async_session_maker() as session:
            query = select(Task)

            # Apply filters
            if state:
                query = query.where(Task.state == state)
            if name:
                query = query.where(Task.name == name)
            if worker:
                query = query.where(Task.worker == worker)
            if since:
                since_dt = datetime.fromisoformat(since)
                query = query.where(Task.created_at >= since_dt)

            # Apply limit
            query = query.limit(limit)

            # Order by created_at descending
            query = query.order_by(Task.created_at.desc())

            result = await session.execute(query)
            tasks = result.scalars().all()

            # Format response
            task_list = []
            for task in tasks:
                task_list.append(
                    {
                        "id": str(task.id),
                        "name": task.name,
                        "state": task.state,
                        "worker": task.worker,
                        "queue": task.queue,
                        "started_at": task.started_at.isoformat() if task.started_at else None,
                        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                        "runtime": task.runtime,
                        "created_at": task.created_at.isoformat(),
                    }
                )

            return task_list

    @server.tool(
        name="get_task",
        description="Get detailed information about a specific task",
    )
    async def get_task(task_id: str) -> dict:
        """Get detailed information about a specific task.

        Args:
            task_id: UUID of the task
        """
        from sqlalchemy import select

        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return {"error": f"Invalid task_id format: {task_id}"}

        async with async_session_maker() as session:
            query = select(Task).where(Task.id == task_uuid)
            result = await session.execute(query)
            task = result.scalar_one_or_none()

            if not task:
                return {"error": f"Task not found: {task_id}"}

            return {
                "id": str(task.id),
                "name": task.name,
                "state": task.state,
                "args": task.args,
                "kwargs": task.kwargs,
                "result": task.result,
                "traceback": task.traceback,
                "worker": task.worker,
                "queue": task.queue,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                "runtime": task.runtime,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat(),
            }

    @server.tool(
        name="get_task_summary",
        description="Get aggregate task statistics",
    )
    async def get_task_summary(hours: int = 1) -> dict:
        """Get aggregate task statistics.

        Args:
            hours: Time window in hours (default: 1)
        """
        from sqlalchemy import and_, func, select

        since = datetime.now(UTC) - timedelta(hours=hours)

        async with async_session_maker() as session:
            # Count tasks by state
            query = (
                select(Task.state, func.count(Task.id))
                .where(Task.created_at >= since)
                .group_by(Task.state)
            )
            result = await session.execute(query)
            state_counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

            # Calculate average runtime for successful tasks
            query = select(func.avg(Task.runtime)).where(
                and_(
                    Task.state == "SUCCESS",
                    Task.created_at >= since,
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

    @server.tool(
        name="get_worker_status",
        description="Get status of all Celery workers",
    )
    async def get_worker_status() -> list[dict]:
        """Get status of all Celery workers."""
        from sqlalchemy import select

        async with async_session_maker() as session:
            query = select(Worker).order_by(Worker.hostname)
            result = await session.execute(query)
            workers = result.scalars().all()

            worker_list = []
            for worker in workers:
                worker_list.append(
                    {
                        "hostname": worker.hostname,
                        "status": worker.status,
                        "pool_size": worker.pool_size,
                        "active_count": worker.active_count,
                        "processed_count": worker.processed_count,
                        "last_heartbeat": (
                            worker.last_heartbeat.isoformat() if worker.last_heartbeat else None
                        ),
                    }
                )

            return worker_list
