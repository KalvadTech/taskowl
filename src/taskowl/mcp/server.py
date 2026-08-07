"""MCP server for taskowl.

This module sets up the MCP server that exposes taskowl tools to LLMs.
"""

import logging

from mcp.server import MCPServer

from taskowl.config import settings
from taskowl.mcp.tools import register_tools

logger = logging.getLogger(__name__)


def create_mcp_server() -> MCPServer:
    """Create and configure the MCP server."""
    server = MCPServer("taskowl")
    register_tools(server)
    logger.info("MCP server created with taskowl tools")
    return server


async def run_mcp_server() -> None:
    """Run the MCP server."""
    if not settings.mcp_enabled:
        logger.info("MCP server is disabled")
        return

    server = create_mcp_server()
    logger.info(f"Starting MCP server on {settings.mcp_host}:{settings.mcp_port}")

    # Run the server using stdio transport (for Claude Desktop integration)
    server.run(transport="stdio")
