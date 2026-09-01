"""Main entry point for taskowl."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.actions import retry_task, revoke_task
from taskowl.auth import verify_api_key
from taskowl.config import settings
from taskowl.database import close_db, get_db, init_db
from taskowl.metrics import generate_metrics
from taskowl.queries import (
    get_task_chain_query,
    get_task_query,
    get_task_summary_query,
    get_task_timeline_query,
    get_worker_status_query,
    list_orphaned_tasks_query,
    list_task_types_query,
    list_tasks_query,
)
from taskowl.workers import (
    get_active_tasks,
    get_worker_stats,
    list_workers,
    scale_worker_pool,
    shutdown_worker,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle."""
    logger.info("Starting taskowl...")
    await init_db()
    logger.info("Database initialized")

    yield

    # Cleanup
    logger.info("Shutting down taskowl...")
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="taskowl",
    description="Modern Celery task monitoring with MCP integration",
    version="0.1.0",
    lifespan=lifespan,
)


class TaskSummary(BaseModel):
    """Task summary response model."""

    period_hours: int
    total_tasks: int
    by_state: dict[str, int]
    avg_runtime_seconds: float | None


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# NOTE: This endpoint is intentionally UNAUTHENTICATED so Prometheus can
# scrape it without sending the taskowl API key. Ensure it is only reachable
# from trusted networks or behind a reverse proxy.
# TODO: consider network-level auth or a separate scraper token if exposed
# beyond a trusted network.
@app.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_db)) -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=await generate_metrics(session),
        media_type="text/plain; version=0.0.4",
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": "taskowl",
        "version": "0.1.0",
        "description": "Modern Celery task monitoring with MCP integration",
        "docs": "/docs",
    }


# REST API endpoints


@app.get("/api/tasks")
async def api_list_tasks(
    state: str | None = None,
    name: str | None = None,
    worker: str | None = None,
    since: str | None = None,
    limit: int = 100,
    search: str | None = None,
    offset: int = 0,
    sort_by: str = "timestamp",
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> list[dict] | dict:
    """List tasks with optional filters."""
    result = await list_tasks_query(
        state, name, worker, since, limit, search, offset, sort_by, session
    )
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/tasks/types")
async def api_list_task_types(
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> list[dict]:
    """List distinct task names (types) with their task counts."""
    return await list_task_types_query(limit, session)


@app.get("/api/tasks/summary")
async def api_get_task_summary(
    hours: int = 1,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> TaskSummary:
    """Get aggregate task statistics."""
    result = await get_task_summary_query(hours, session)
    return TaskSummary(**result)


@app.get("/api/tasks/orphaned")
async def api_list_orphaned_tasks(
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> list[dict]:
    """List tasks currently considered orphaned."""
    return await list_orphaned_tasks_query(limit, session)


@app.get("/api/tasks/{task_id}")
async def api_get_task(
    task_id: str,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> dict:
    """Get detailed information about a specific task."""
    result = await get_task_query(task_id, session)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/tasks/{task_id}/timeline")
async def api_get_task_timeline(
    task_id: str,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> list[dict]:
    """Get chronological timeline of all events for a task."""
    result = await get_task_timeline_query(task_id, session)
    if result and "error" in result[0]:
        raise HTTPException(status_code=404, detail=result[0]["error"])
    return result


@app.get("/api/tasks/{task_id}/chain")
async def api_get_task_chain(
    task_id: str,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> dict:
    """Get the full retry chain for a task."""
    result = await get_task_chain_query(task_id, session)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/workers")
async def api_get_worker_status(
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> list[dict]:
    """Get status of all Celery workers."""
    return await get_worker_status_query(session)


@app.post("/api/tasks/{task_id}/revoke")
async def api_revoke_task(
    task_id: str,
    terminate: bool = False,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> dict:
    """Revoke (cancel) a task.

    Args:
        task_id: UUID of the task to revoke
        terminate: If True, terminate the task if it's currently running
    """
    result = await revoke_task(task_id, terminate, session)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/tasks/{task_id}/retry")
async def api_retry_task(
    task_id: str,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
) -> dict:
    """Retry a failed or revoked task.

    Args:
        task_id: UUID of the task to retry
    """
    result = await retry_task(task_id, session)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/workers/list")
async def api_list_workers(
    _: None = Depends(verify_api_key),
) -> dict:
    """List all active Celery workers."""
    return await list_workers()


@app.get("/api/workers/{worker_name}/stats")
async def api_get_worker_stats(
    worker_name: str,
    _: None = Depends(verify_api_key),
) -> dict:
    """Get statistics for a specific worker.

    Args:
        worker_name: Name of the worker (e.g., 'celery@worker1')
    """
    result = await get_worker_stats(worker_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/api/workers/{worker_name}/shutdown")
async def api_shutdown_worker(
    worker_name: str,
    _: None = Depends(verify_api_key),
) -> dict:
    """Gracefully shutdown a worker.

    Args:
        worker_name: Name of the worker to shutdown
    """
    result = await shutdown_worker(worker_name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/workers/{worker_name}/scale")
async def api_scale_worker_pool(
    worker_name: str,
    delta: int,
    _: None = Depends(verify_api_key),
) -> dict:
    """Scale worker pool up or down.

    Args:
        worker_name: Name of the worker
        delta: Number of processes to add (positive) or remove (negative)
    """
    result = await scale_worker_pool(worker_name, delta)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/workers/active-tasks")
async def api_get_active_tasks(
    worker_name: str | None = None,
    _: None = Depends(verify_api_key),
) -> dict:
    """Get currently executing tasks.

    Args:
        worker_name: Optional worker name to filter by
    """
    return await get_active_tasks(worker_name)


# MCP server is now run separately via taskowl-mcp command
# See taskowl.mcp.server:run_mcp_server()


def main() -> None:
    """Main entry point."""
    # Run FastAPI server
    logger.info(f"Starting FastAPI server on {settings.taskowl_host}:{settings.taskowl_port}")
    uvicorn.run(
        "taskowl.main:app",
        host=settings.taskowl_host,
        port=settings.taskowl_port,
        reload=settings.log_level == "DEBUG",
    )


if __name__ == "__main__":
    main()
