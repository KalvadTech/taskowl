"""CLI entry point for the Celery event consumer."""

import asyncio
import logging

from taskowl.config import settings
from taskowl.consumer.receiver import CeleryEventConsumer

logger = logging.getLogger(__name__)


async def run_consumer() -> None:
    """Run the Celery event consumer."""
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting taskowl consumer...")
    logger.info(f"Broker URL: {settings.celery_broker_url}")

    consumer = CeleryEventConsumer(settings.celery_broker_url)
    await consumer.start()


def main() -> None:
    """Main entry point for the consumer CLI."""
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
