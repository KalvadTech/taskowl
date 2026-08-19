"""Worker management functions for taskowl.

This module provides functions to manage Celery workers remotely,
including listing workers, getting stats, shutting down workers,
and scaling worker pools.
"""

from celery import Celery

from taskowl.config import settings


def _get_celery_app() -> Celery:
    """Get Celery app instance configured with broker URL."""
    return Celery(broker=settings.celery_broker_url)


async def list_workers() -> dict:
    """List all active Celery workers.

    Returns:
        Dict with list of workers and their status
    """
    try:
        app = _get_celery_app()
        inspect = app.control.inspect()

        # Ping workers to see who's alive
        ping_result = inspect.ping()

        if not ping_result:
            return {"workers": []}

        workers = []
        for worker_name, status in ping_result.items():
            workers.append(
                {
                    "name": worker_name,
                    "status": "online" if status else "offline",
                }
            )

        return {"workers": workers}
    except Exception as e:
        return {"error": f"Failed to list workers: {str(e)}"}


async def get_worker_stats(worker_name: str) -> dict:
    """Get detailed statistics for a specific worker.

    Args:
        worker_name: Name of the worker (e.g., 'celery@worker1')

    Returns:
        Dict with worker statistics
    """
    try:
        app = _get_celery_app()
        inspect = app.control.inspect(destination=[worker_name])

        stats = inspect.stats()

        if not stats or worker_name not in stats:
            return {"error": f"Worker {worker_name} not found or not responding"}

        return {"stats": stats[worker_name]}
    except Exception as e:
        return {"error": f"Failed to get worker stats: {str(e)}"}


async def shutdown_worker(worker_name: str) -> dict:
    """Gracefully shutdown a worker.

    Args:
        worker_name: Name of the worker to shutdown

    Returns:
        Dict with status and message
    """
    try:
        app = _get_celery_app()
        app.control.shutdown(destination=[worker_name])

        return {
            "status": "success",
            "message": f"Shutdown command sent to {worker_name}",
        }
    except Exception as e:
        return {"error": f"Failed to shutdown worker: {str(e)}"}


async def scale_worker_pool(worker_name: str, delta: int) -> dict:
    """Scale worker pool up or down.

    Args:
        worker_name: Name of the worker
        delta: Number of processes to add (positive) or remove (negative)

    Returns:
        Dict with status and message
    """
    if delta == 0:
        return {"error": "Delta must be non-zero"}

    try:
        app = _get_celery_app()

        if delta > 0:
            # Grow pool
            app.control.pool_grow(n=delta, destination=[worker_name])
            action = "grown"
        else:
            # Shrink pool
            app.control.pool_shrink(n=abs(delta), destination=[worker_name])
            action = "shrunk"

        return {
            "status": "success",
            "message": f"Worker pool {action} by {abs(delta)}",
            "worker": worker_name,
            "delta": delta,
        }
    except Exception as e:
        return {"error": f"Failed to scale worker pool: {str(e)}"}


async def get_active_tasks(worker_name: str | None = None) -> dict:
    """Get currently executing tasks.

    Args:
        worker_name: Optional worker name to filter by

    Returns:
        Dict with active tasks grouped by worker
    """
    try:
        app = _get_celery_app()
        inspect = app.control.inspect()

        if worker_name:
            inspect = inspect.destination([worker_name])

        active = inspect.active()

        return {"active_tasks": active or {}}
    except Exception as e:
        return {"error": f"Failed to get active tasks: {str(e)}"}
