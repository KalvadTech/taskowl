"""Simple alerting + webhook notification system.

Fires Slack-compatible webhook notifications in response to Celery events
(task failures, slow tasks, offline workers). Everything is opt-in via
environment variables; if no webhook URL is configured, alerting is a no-op.
"""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.config import settings
from taskowl.database import async_session_maker
from taskowl.models import WorkerEvent

logger = logging.getLogger(__name__)

_COLOR_FAILURE = "danger"
_COLOR_WARNING = "warning"


class WebhookClient:
    """Sends alerts to a Slack-compatible webhook. Never raises."""

    def __init__(self, url: str) -> None:
        self.url = url

    async def send(self, payload: dict) -> None:
        """POST the payload to the webhook, logging failures instead of raising."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.url, json=payload, timeout=10.0)
                response.raise_for_status()
        except Exception:
            logger.exception("Failed to send alert to webhook %s", self.url)


def _field(title: str, value: object, short: bool = True) -> dict:
    """Build a Slack attachment field."""
    return {"title": title, "value": str(value or "unknown"), "short": short}


def build_task_failed_payload(event: dict) -> dict:
    """Build a Slack payload for a task-failed event."""
    return {
        "text": "⚠️ Task failed",
        "attachments": [
            {
                "color": _COLOR_FAILURE,
                "fields": [
                    _field("Task", event.get("name")),
                    _field("Task ID", event.get("uuid")),
                    _field("Worker", event.get("hostname")),
                    _field("Error", event.get("exception"), short=False),
                ],
            }
        ],
    }


def build_worker_offline_payload(hostname: str, last_heartbeat: datetime | None = None) -> dict:
    """Build a Slack payload for a worker-offline alert."""
    last_hb = last_heartbeat.isoformat() if last_heartbeat else "unknown"
    return {
        "text": "⚠️ Worker offline",
        "attachments": [
            {
                "color": _COLOR_FAILURE,
                "fields": [
                    _field("Worker", hostname),
                    _field("Last heartbeat", last_hb),
                ],
            }
        ],
    }


def build_slow_task_payload(event: dict) -> dict:
    """Build a Slack payload for a slow-task alert."""
    return {
        "text": "🐢 Slow task detected",
        "attachments": [
            {
                "color": _COLOR_WARNING,
                "fields": [
                    _field("Task", event.get("name")),
                    _field("Task ID", event.get("uuid")),
                    _field("Runtime (s)", event.get("runtime")),
                    _field("Worker", event.get("hostname")),
                ],
            }
        ],
    }


class AlertNotifier:
    """Dispatches alerts based on enabled conditions, with worker dedupe."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or settings.alert_webhook_url
        self.enabled = bool(self.webhook_url)
        self._offline_notified: set[str] = set()

        if self.enabled:
            url = self.webhook_url
            assert url is not None  # enabled implies a URL is set
            self._client = WebhookClient(url)
        else:
            self._client = None

    async def notify_event(self, event_type: str, event: dict) -> None:
        """Handle an event: fire alerts for matching conditions."""
        if not self.enabled or self._client is None:
            return

        if event_type == "task-failed" and settings.alert_on_task_failed:
            await self._client.send(build_task_failed_payload(event))

        elif event_type == "task-succeeded" and settings.alert_slow_task_seconds is not None:
            runtime = event.get("runtime")
            if isinstance(runtime, (int, float)) and runtime > settings.alert_slow_task_seconds:
                await self._client.send(build_slow_task_payload(event))

        elif event_type == "worker-offline" and settings.alert_on_worker_offline:
            await self._alert_worker_offline(event.get("hostname"))

    def mark_online(self, hostname: str) -> None:
        """Record that a worker is seen online, allowing future offline alerts."""
        self._offline_notified.discard(hostname)

    async def check_workers(self, now: datetime | None = None) -> None:
        """Periodic sweep: alert for workers whose heartbeat has gone stale."""
        if not self.enabled or self._client is None or not settings.alert_on_worker_offline:
            return

        now = now or datetime.now(UTC)
        offline_timeout = timedelta(seconds=settings.worker_offline_timeout_seconds)

        async with async_session_maker() as session:
            result = await session.execute(select(WorkerEvent.hostname).distinct())
            hostnames = [row[0] for row in result.all()]

            for hostname in hostnames:
                if hostname in self._offline_notified:
                    continue
                if await self._worker_stale(session, hostname, now, offline_timeout):
                    await self._alert_worker_offline(hostname)

    async def _alert_worker_offline(self, hostname: str | None) -> None:
        if not hostname or hostname in self._offline_notified:
            return
        if self._client is None:
            return
        self._offline_notified.add(hostname)
        await self._client.send(build_worker_offline_payload(hostname))

    @staticmethod
    async def _worker_stale(
        session: AsyncSession, hostname: str, now: datetime, offline_timeout: timedelta
    ) -> bool:
        """Check whether a worker's latest event indicates it is stale/offline."""
        query = (
            select(WorkerEvent)
            .where(WorkerEvent.hostname == hostname)
            .order_by(WorkerEvent.timestamp.desc())
            .limit(1)
        )
        result = await session.execute(query)
        event = result.scalar_one_or_none()
        if event is None:
            return True
        if event.event_type == "offline":
            return True
        # Normalize timezone (SQLite returns naive datetimes)
        ts = event.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return now - ts > offline_timeout
