"""Main entry point for taskowl."""

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from taskowl.config import settings
from taskowl.database import close_db, init_db
from taskowl.mcp.server import run_mcp_server

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

    # Start MCP server in background if enabled
    mcp_task = None
    if settings.mcp_enabled:
        mcp_task = asyncio.create_task(run_mcp_server())
        logger.info("MCP server started")

    yield

    # Cleanup
    logger.info("Shutting down taskowl...")
    if mcp_task:
        mcp_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await mcp_task
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="taskowl",
    description="Modern Celery task monitoring with MCP integration",
    version="0.1.0",
    lifespan=lifespan,
)


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


def main() -> None:
    """Main entry point."""
    # Check if running in MCP-only mode
    if "--mcp-only" in sys.argv:
        logger.info("Running in MCP-only mode")
        asyncio.run(run_mcp_server())
        return

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
