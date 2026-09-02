"""Broker queue monitoring functions for taskowl.

This module provides functions to inspect Celery broker queues,
including message counts and consumer counts. It works with any
kombu-supported broker (RabbitMQ, Redis, ...).
"""

import asyncio
import logging

from celery import Celery
from kombu import Connection, Queue

from taskowl.config import settings

logger = logging.getLogger(__name__)


def _get_celery_app() -> Celery:
    """Get Celery app instance configured with broker URL."""
    return Celery(broker=settings.celery_broker_url)


def _declared_queues(app: Celery) -> list[str]:
    """Return the queue names declared by the Celery app.

    Falls back to the app's default queue name if the app exposes no
    explicit queue configuration.
    """
    queues = getattr(app.amqp, "queues", None)
    if queues:
        return list(queues.keys())
    return [app.conf.task_default_queue or "celery"]


def _list_queues_sync() -> dict:
    """Synchronously inspect broker queues and return queue statistics."""
    app = _get_celery_app()
    queue_names = _declared_queues(app)

    with Connection(settings.celery_broker_url) as conn:
        channel = conn.channel()
        queue_stats: list[dict] = []
        for name in queue_names:
            declared = Queue(name).queue_declare(channel=channel, passive=True)
            messages: int = int(getattr(declared, "message_count", 0))
            consumers: int = int(getattr(declared, "consumer_count", 0))
            queue_stats.append(
                {
                    "name": name,
                    "messages": messages,
                    "consumers": consumers,
                }
            )

    queue_stats.sort(key=lambda q: q["messages"], reverse=True)
    total_messages: int = sum(int(q["messages"]) for q in queue_stats)
    return {
        "queues": queue_stats,
        "total_messages": total_messages,
    }


async def list_queues() -> dict:
    """List Celery broker queues with message and consumer counts.

    Returns:
        Dict with a queue list and a total message count. On broker
        failure, returns an error dict.
    """
    try:
        # Broker I/O is synchronous; offload to a thread to keep the
        # event loop responsive.
        return await asyncio.to_thread(_list_queues_sync)
    except Exception as e:
        logger.exception("Failed to list broker queues")
        return {"error": f"Failed to list queues: {str(e)}"}
