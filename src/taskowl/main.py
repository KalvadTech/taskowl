"""Main entry point for taskowl."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.config import settings
from taskowl.database import close_db, get_db, init_db
from taskowl.queries import (
    get_task_query,
    get_task_summary_query,
    get_task_timeline_query,
    get_worker_status_query,
    list_tasks_query,
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
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List tasks with optional filters."""
    return await list_tasks_query(state, name, worker, since, limit, session)


@app.get("/api/tasks/summary")
async def api_get_task_summary(
    hours: int = 1, session: AsyncSession = Depends(get_db)
) -> TaskSummary:
    """Get aggregate task statistics."""
    result = await get_task_summary_query(hours, session)
    return TaskSummary(**result)


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Get detailed information about a specific task."""
    result = await get_task_query(task_id, session)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/tasks/{task_id}/timeline")
async def api_get_task_timeline(
    task_id: str, session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Get chronological timeline of all events for a task."""
    result = await get_task_timeline_query(task_id, session)
    if result and "error" in result[0]:
        raise HTTPException(status_code=404, detail=result[0]["error"])
    return result


@app.get("/api/workers")
async def api_get_worker_status(
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get status of all Celery workers."""
    return await get_worker_status_query(session)


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
