"""MCP tools for taskowl.

This module defines the MCP tools that can be used by LLMs to query
task and worker information. These tools call the REST API endpoints.
"""

import httpx
from mcp.server import MCPServer

from taskowl.config import settings


def _get_headers() -> dict[str, str]:
    """Get HTTP headers for API requests, including auth if configured."""
    headers: dict[str, str] = {}
    if settings.api_key is not None:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


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
            state: Filter by state (received, started, succeeded, failed, retried, revoked)
            name: Filter by task name
            worker: Filter by worker hostname
            since: Only tasks created after this datetime (ISO 8601)
            limit: Max number of tasks to return (default: 100)
        """
        async with httpx.AsyncClient() as client:
            params = {"limit": limit}
            if state is not None:
                params["state"] = state
            if name is not None:
                params["name"] = name
            if worker is not None:
                params["worker"] = worker
            if since is not None:
                params["since"] = since

            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/tasks",
                params=params,
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="list_orphaned_tasks",
        description=(
            "List tasks currently considered orphaned (stuck in STARTED with worker offline)"
        ),
    )
    async def list_orphaned_tasks(limit: int = 100) -> list[dict]:
        """List tasks currently considered orphaned.

        Args:
            limit: Max number of tasks to return (default: 100)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/tasks/orphaned",
                params={"limit": limit},
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="get_task",
        description="Get detailed information about a specific task",
    )
    async def get_task(task_id: str) -> dict:
        """Get detailed information about a specific task.

        Args:
            task_id: UUID of the task
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/tasks/{task_id}",
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="get_task_timeline",
        description="Get chronological timeline of all events for a task",
    )
    async def get_task_timeline(task_id: str) -> list[dict]:
        """Get all events for a task in chronological order.

        Args:
            task_id: UUID of the task
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/tasks/{task_id}/timeline",
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="get_task_summary",
        description="Get aggregate task statistics",
    )
    async def get_task_summary(hours: int = 1) -> dict:
        """Get aggregate task statistics.

        Args:
            hours: Time window in hours (default: 1)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/tasks/summary",
                params={"hours": hours},
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="get_worker_status",
        description="Get status of all Celery workers",
    )
    async def get_worker_status() -> list[dict]:
        """Get status of all Celery workers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/workers",
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="revoke_task",
        description="Revoke (cancel) a task. Optionally terminate if currently running.",
    )
    async def revoke_task(task_id: str, terminate: bool = False) -> dict:
        """Revoke (cancel) a task.

        Args:
            task_id: UUID of the task to revoke
            terminate: If True, terminate the task if it's currently running
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/tasks/{task_id}/revoke",
                params={"terminate": terminate},
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="retry_task",
        description=(
            "Retry a failed or revoked task by creating a new task with the same parameters."
        ),
    )
    async def retry_task(task_id: str) -> dict:
        """Retry a failed or revoked task.

        Args:
            task_id: UUID of the task to retry
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/tasks/{task_id}/retry",
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="list_workers",
        description="List all active Celery workers",
    )
    async def list_workers() -> dict:
        """List all active Celery workers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/workers/list",
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="get_worker_stats",
        description="Get detailed statistics for a specific worker",
    )
    async def get_worker_stats(worker_name: str) -> dict:
        """Get detailed statistics for a specific worker.

        Args:
            worker_name: Name of the worker (e.g., 'celery@worker1')
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/workers/{worker_name}/stats",
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="shutdown_worker",
        description="Gracefully shutdown a Celery worker",
    )
    async def shutdown_worker(worker_name: str) -> dict:
        """Gracefully shutdown a Celery worker.

        Args:
            worker_name: Name of the worker to shutdown
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/workers/{worker_name}/shutdown",
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="scale_worker_pool",
        description="Scale a worker's pool size up or down",
    )
    async def scale_worker_pool(worker_name: str, delta: int) -> dict:
        """Scale a worker's pool size up or down.

        Args:
            worker_name: Name of the worker
            delta: Number of processes to add (positive) or remove (negative)
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/workers/{worker_name}/scale",
                params={"delta": delta},
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        name="get_active_tasks",
        description="Get currently executing tasks across all workers or a specific worker",
    )
    async def get_active_tasks(worker_name: str | None = None) -> dict:
        """Get currently executing tasks.

        Args:
            worker_name: Optional worker name to filter by
        """
        async with httpx.AsyncClient() as client:
            params = {}
            if worker_name:
                params["worker_name"] = worker_name

            response = await client.get(
                f"http://{settings.taskowl_host}:{settings.taskowl_port}/api/workers/active-tasks",
                params=params,
                headers=_get_headers(),
            )
            response.raise_for_status()
            return response.json()
