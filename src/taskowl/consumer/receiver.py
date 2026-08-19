"""Celery event receiver.

This module sets up the Celery event receiver and handles event processing
with reconnection logic and graceful shutdown.
"""

import asyncio
import contextlib
import logging
import signal
from typing import Any

from celery import Celery
from celery.events import EventReceiver
from kombu import Connection

from taskowl.config import settings
from taskowl.consumer.handlers import (
    TASK_EVENT_HANDLERS,
    WORKER_EVENT_HANDLERS,
)
from taskowl.database import async_session_maker

logger = logging.getLogger(__name__)


class CeleryEventConsumer:
    """Consumes Celery events and stores them in the database."""

    def __init__(self, broker_url: str) -> None:
        """Initialize the consumer.

        Args:
            broker_url: Celery broker connection string
        """
        self.broker_url = broker_url
        self.app = Celery(broker=broker_url)
        self.running = False
        self.shutdown_event = asyncio.Event()
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self.connection: Connection | None = None
        self.recv: EventReceiver | None = None

    def _create_handlers(self) -> dict[str, Any]:
        """Create event handler mapping for Celery receiver."""
        handlers = {}

        # Add task event handlers
        for event_type, handler_func in TASK_EVENT_HANDLERS.items():
            handlers[event_type] = self._make_handler_wrapper(handler_func)

        # Add worker event handlers
        for event_type, handler_func in WORKER_EVENT_HANDLERS.items():
            handlers[event_type] = self._make_handler_wrapper(handler_func)

        return handlers

    def _make_handler_wrapper(self, handler_func: Any) -> Any:
        """Create a wrapper that schedules async handler on main event loop."""

        def wrapper(event: dict) -> None:
            """Wrapper to schedule async handler."""
            if not self.running or self._main_loop is None:
                return

            # Schedule the async handler on the main event loop
            asyncio.run_coroutine_threadsafe(
                self._handle_event(event, handler_func),
                self._main_loop,
            )

        return wrapper

    async def _handle_event(self, event: dict, handler_func: Any) -> None:
        """Handle a single event."""
        try:
            async with async_session_maker() as session:
                await handler_func(event, session)
        except Exception:
            logger.exception(f"Error handling event: {event}")

    def _capture_events(self) -> None:
        """Capture events from Celery broker."""
        handlers = self._create_handlers()

        while self.running and not self.shutdown_event.is_set():
            try:
                self.connection = Connection(self.broker_url)
                with self.connection:
                    logger.info("Connected to Celery broker")

                    def on_event(event: dict) -> None:
                        """Process a single event."""
                        event_type = event.get("type")
                        if event_type in handlers:
                            handlers[event_type](event)

                    self.recv = self.app.events.Receiver(
                        self.connection,
                        handlers={
                            "*": on_event,
                        },
                    )

                    logger.info("Starting to capture Celery events...")
                    self.recv.capture(limit=None, timeout=None, wakeup=True)

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                break
            except Exception:
                if not self.running or self.shutdown_event.is_set():
                    break
                logger.exception("Error in event capture, reconnecting in 5 seconds...")
                # Wait before reconnecting
                for _ in range(50):  # 5 seconds with 0.1s intervals
                    if self.shutdown_event.is_set():
                        break
                    import time

                    time.sleep(0.1)
            finally:
                self.connection = None
                self.recv = None

    async def start(self) -> None:
        """Start consuming events."""
        logger.info("Starting Celery event consumer...")
        self.running = True

        # Store reference to the main event loop for thread-safe scheduling
        self._main_loop = asyncio.get_running_loop()

        # Set up signal handlers
        loop = asyncio.get_running_loop()

        def handle_signal() -> None:
            logger.info("Received shutdown signal")
            self.running = False
            self.shutdown_event.set()

            # Graceful shutdown using Celery's built-in mechanism
            if self.recv:
                self.recv.should_stop = True
            if self.connection:
                with contextlib.suppress(Exception):
                    self.connection.close()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

        # Run event capture in thread pool to avoid blocking
        await asyncio.to_thread(self._capture_events)

        logger.info("Celery event consumer stopped")

    async def stop(self) -> None:
        """Stop consuming events."""
        logger.info("Stopping Celery event consumer...")
        self.running = False
        self.shutdown_event.set()


async def start_consumer() -> None:
    """Start the Celery event consumer."""
    consumer = CeleryEventConsumer(settings.celery_broker_url)
    await consumer.start()
