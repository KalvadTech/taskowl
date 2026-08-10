"""MCP server CLI for taskowl."""

import logging

from taskowl.config import settings
from taskowl.mcp.server import run_mcp_server

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the MCP server CLI."""
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting taskowl MCP server...")
    run_mcp_server()


if __name__ == "__main__":
    main()
