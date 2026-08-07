"""MCP server for taskowl.

This module sets up the MCP server that exposes taskowl tools to LLMs.
"""

import logging

from mcp.server import MCPServer
from starlette.applications import Starlette

from taskowl.mcp.tools import register_tools

logger = logging.getLogger(__name__)


def create_mcp_server() -> MCPServer:
    """Create and configure the MCP server."""
    server = MCPServer("taskowl")
    register_tools(server)
    logger.info("MCP server created with taskowl tools")
    return server


def build_mcp_app() -> Starlette:
    """Build the MCP ASGI application."""
    server = create_mcp_server()
    app: Starlette = server.streamable_http_app(stateless_http=True, json_response=True)
    logger.info("MCP ASGI application built")
    return app
