"""Main entry point for taskowl."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.applications import Starlette

from taskowl.config import settings
from taskowl.database import close_db, init_db
from taskowl.mcp.server import build_mcp_app

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


# Mount MCP application at /mcp
mcp_app: Starlette = build_mcp_app()
app.mount("/mcp", mcp_app)


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
