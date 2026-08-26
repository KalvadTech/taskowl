"""Tests for the alerting + webhook system."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskowl.alerting import (
    AlertNotifier,
    WebhookClient,
    build_slow_task_payload,
    build_task_failed_payload,
    build_worker_offline_payload,
)


def test_task_failed_payload_metadata_only():
    """Task-failed payload should contain metadata only."""
    payload = build_task_failed_payload(
        {
            "uuid": "abc-123",
            "name": "myapp.tasks.process",
            "hostname": "celery@worker1",
            "exception": "ValueError: bad input",
        }
    )
    assert payload["text"] == "⚠️ Task failed"
    fields = {f["title"]: f["value"] for f in payload["attachments"][0]["fields"]}
    assert fields["Task"] == "myapp.tasks.process"
    assert fields["Task ID"] == "abc-123"
    assert fields["Worker"] == "celery@worker1"
    assert fields["Error"] == "ValueError: bad input"


def test_worker_offline_payload():
    """Worker-offline payload should contain hostname and heartbeat."""
    hb = datetime(2026, 1, 1, tzinfo=UTC)
    payload = build_worker_offline_payload("celery@worker1", hb)
    assert payload["text"] == "⚠️ Worker offline"
    fields = {f["title"]: f["value"] for f in payload["attachments"][0]["fields"]}
    assert fields["Worker"] == "celery@worker1"
    assert fields["Last heartbeat"] == "2026-01-01T00:00:00+00:00"


def test_slow_task_payload():
    """Slow-task payload should contain task metadata and runtime."""
    payload = build_slow_task_payload(
        {
            "uuid": "xyz",
            "name": "myapp.tasks.slow",
            "hostname": "celery@worker1",
            "runtime": 123.4,
        }
    )
    assert payload["text"] == "🐢 Slow task detected"
    fields = {f["title"]: f["value"] for f in payload["attachments"][0]["fields"]}
    assert fields["Runtime (s)"] == "123.4"


@pytest.mark.asyncio
async def test_webhook_send_success():
    """WebhookClient should POST the payload to the URL."""
    client = WebhookClient("https://hooks.slack.com/test")
    with patch("taskowl.alerting.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(status_code=200)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        await client.send({"text": "hi"})

        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == "https://hooks.slack.com/test"
        assert kwargs["json"] == {"text": "hi"}


@pytest.mark.asyncio
async def test_webhook_send_failure_does_not_raise():
    """WebhookClient should swallow httpx failures."""
    client = WebhookClient("https://hooks.slack.com/test")
    with patch("taskowl.alerting.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("boom")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Should not raise
        await client.send({"text": "hi"})


@pytest.mark.asyncio
async def test_notifier_disabled_is_noop():
    """With no webhook URL, notifier should do nothing."""
    notifier = AlertNotifier(webhook_url=None)
    with patch.object(notifier, "_client") as mock_client:
        assert notifier.enabled is False
        await notifier.notify_event("task-failed", {"uuid": "x"})
        mock_client.send.assert_not_called()


@pytest.mark.asyncio
async def test_notifier_task_failed_fires():
    """Task-failed alert should fire when enabled."""
    notifier = AlertNotifier(webhook_url="https://hooks.slack.com/test")
    notifier._client = AsyncMock()
    notifier._client.send = AsyncMock()

    await notifier.notify_event(
        "task-failed", {"uuid": "x", "name": "t", "hostname": "w", "exception": "e"}
    )
    notifier._client.send.assert_called_once()


@pytest.mark.asyncio
async def test_notifier_slow_task_threshold():
    """Slow-task alert should respect the threshold."""
    notifier = AlertNotifier(webhook_url="https://hooks.slack.com/test")
    notifier._client = AsyncMock()
    notifier._client.send = AsyncMock()

    with patch("taskowl.alerting.settings.alert_slow_task_seconds", 10.0):
        await notifier.notify_event("task-succeeded", {"uuid": "x", "runtime": 5.0})
        notifier._client.send.assert_not_called()

        await notifier.notify_event("task-succeeded", {"uuid": "x", "runtime": 15.0})
        assert notifier._client.send.call_count == 1


@pytest.mark.asyncio
async def test_notifier_worker_offline_dedupe():
    """Worker offline should alert once, and again after mark_online."""
    notifier = AlertNotifier(webhook_url="https://hooks.slack.com/test")
    notifier._client = AsyncMock()
    notifier._client.send = AsyncMock()

    await notifier.notify_event("worker-offline", {"hostname": "celery@w1"})
    await notifier.notify_event("worker-offline", {"hostname": "celery@w1"})
    assert notifier._client.send.call_count == 1

    notifier.mark_online("celery@w1")
    await notifier.notify_event("worker-offline", {"hostname": "celery@w1"})
    assert notifier._client.send.call_count == 2


@pytest.mark.asyncio
async def test_check_workers_detects_stale(db_session):
    """Periodic check should alert for workers with stale heartbeats."""
    from taskowl.alerting import AlertNotifier
    from taskowl.models import WorkerEvent

    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="celery@w1",
            timestamp=datetime.now(UTC) - timedelta(seconds=300),
        )
    )
    await db_session.commit()

    notifier = AlertNotifier(webhook_url="https://hooks.slack.com/test")
    notifier._client = AsyncMock()
    notifier._client.send = AsyncMock()

    with (
        patch("taskowl.alerting.settings.alert_on_worker_offline", True),
        patch("taskowl.alerting.async_session_maker", return_value=db_session),
    ):
        await notifier.check_workers()
        assert notifier._client.send.call_count == 1
        # Second sweep should not re-alert (dedupe)
        await notifier.check_workers()
        assert notifier._client.send.call_count == 1
