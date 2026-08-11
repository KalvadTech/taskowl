"""MCP server for taskowl.

This module sets up the MCP server that exposes taskowl tools to LLMs.
"""

import logging

import uvicorn
from mcp.server import MCPServer

from taskowl.auth import AuthMiddleware
from taskowl.config import settings
from taskowl.mcp.tools import register_tools

logger = logging.getLogger(__name__)


def create_mcp_server() -> MCPServer:
    """Create and configure the MCP server."""
    server = MCPServer("taskowl")
    register_tools(server)
    logger.info("MCP server created with taskowl tools")
    return server


def run_mcp_server() -> None:
    """Run the MCP server as a standalone service."""
    server = create_mcp_server()
    logger.info(f"Starting MCP server on {settings.mcp_host}:{settings.mcp_port}")

    # Get the ASGI app from the server
    app = server.streamable_http_app(stateless_http=True, json_response=True)

    # Wrap with auth middleware
    app = AuthMiddleware(app)

    # Run with uvicorn
    uvicorn.run(
        app,
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.log_level.lower(),
    )
