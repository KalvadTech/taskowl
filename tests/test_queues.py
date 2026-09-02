"""Tests for broker queue monitoring functions."""

from unittest.mock import MagicMock, patch

import pytest

from taskowl.queues import list_queues


def _make_declared(message_count=0, consumer_count=0):
    declared = MagicMock()
    declared.message_count = message_count
    declared.consumer_count = consumer_count
    return declared


@pytest.mark.asyncio
async def test_list_queues_success():
    """Test listing queues with message and consumer counts."""
    mock_connection = MagicMock()
    mock_channel = MagicMock()

    # Two queues: default with messages, secondary empty
    mock_connection.channel.return_value = mock_channel

    declared_default = _make_declared(message_count=5, consumer_count=1)
    declared_secondary = _make_declared(message_count=0, consumer_count=0)

    with (
        patch("taskowl.queues.Connection", return_value=mock_connection),
        patch("taskowl.queues._get_celery_app") as mock_get_app,
        patch("taskowl.queues.Queue") as mock_queue_cls,
    ):
        mock_app = MagicMock()
        mock_app.amqp.queues.keys.return_value = ["default", "secondary"]
        mock_get_app.return_value = mock_app

        def make_queue(name):
            q = MagicMock()
            q.queue_declare.return_value = (
                declared_default if name == "default" else declared_secondary
            )
            return q

        mock_queue_cls.side_effect = make_queue

        result = await list_queues()

    assert "queues" in result
    queues = result["queues"]
    assert len(queues) == 2
    assert queues[0]["name"] == "default"
    assert queues[0]["messages"] == 5
    assert queues[0]["consumers"] == 1
    assert queues[1]["name"] == "secondary"
    assert queues[1]["messages"] == 0
    assert result["total_messages"] == 5


@pytest.mark.asyncio
async def test_list_queues_ordered_by_messages_desc():
    """Test queues are ordered by message count descending."""
    mock_connection = MagicMock()
    mock_connection.channel.return_value = MagicMock()

    with (
        patch("taskowl.queues.Connection", return_value=mock_connection),
        patch("taskowl.queues._get_celery_app") as mock_get_app,
        patch("taskowl.queues.Queue") as mock_queue_cls,
    ):
        mock_app = MagicMock()
        mock_app.amqp.queues.keys.return_value = ["small", "big", "mid"]
        mock_get_app.return_value = mock_app

        counts = {"small": 1, "big": 10, "mid": 5}

        def make_queue(name):
            q = MagicMock()
            q.queue_declare.return_value = _make_declared(
                message_count=counts[name], consumer_count=0
            )
            return q

        mock_queue_cls.side_effect = make_queue

        result = await list_queues()

    names = [q["name"] for q in result["queues"]]
    assert names == ["big", "mid", "small"]


@pytest.mark.asyncio
async def test_list_queues_error():
    """Test listing queues when the broker fails."""
    with patch("taskowl.queues.Connection", side_effect=Exception("Broker down")):
        result = await list_queues()

    assert "error" in result
    assert "Broker down" in result["error"]


@pytest.mark.asyncio
async def test_list_queues_no_queues_configured():
    """Test listing queues when the app exposes no explicit queue config."""
    mock_connection = MagicMock()
    mock_connection.channel.return_value = MagicMock()

    with (
        patch("taskowl.queues.Connection", return_value=mock_connection),
        patch("taskowl.queues._get_celery_app") as mock_get_app,
        patch("taskowl.queues.Queue") as mock_queue_cls,
    ):
        mock_app = MagicMock()
        # Simulate an app without explicit queue config -> use default queue
        mock_app.amqp.queues = None
        mock_app.conf.task_default_queue = "celery"
        mock_get_app.return_value = mock_app

        declared = _make_declared(message_count=3, consumer_count=1)
        mock_queue = MagicMock()
        mock_queue.queue_declare.return_value = declared
        mock_queue_cls.return_value = mock_queue

        result = await list_queues()

    assert len(result["queues"]) == 1
    assert result["queues"][0]["name"] == "celery"
    assert result["queues"][0]["messages"] == 3
    assert result["total_messages"] == 3
