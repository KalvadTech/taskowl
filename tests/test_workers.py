"""Tests for worker management functions."""

from unittest.mock import MagicMock, patch

import pytest

from taskowl.workers import (
    get_active_tasks,
    get_worker_stats,
    list_workers,
    scale_worker_pool,
    shutdown_worker,
)


@pytest.mark.asyncio
async def test_list_workers_success():
    """Test listing workers successfully."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {
            "celery@worker1": {"ok": "pong"},
            "celery@worker2": {"ok": "pong"},
        }
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        result = await list_workers()

        assert "workers" in result
        assert len(result["workers"]) == 2
        assert result["workers"][0]["name"] == "celery@worker1"
        assert result["workers"][0]["status"] == "online"


@pytest.mark.asyncio
async def test_list_workers_no_workers():
    """Test listing workers when none are active."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = None
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        result = await list_workers()

        assert result == {"workers": []}


@pytest.mark.asyncio
async def test_list_workers_error():
    """Test listing workers when an error occurs."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_get_app.side_effect = Exception("Connection failed")

        result = await list_workers()

        assert "error" in result
        assert "Failed to list workers" in result["error"]


@pytest.mark.asyncio
async def test_get_worker_stats_success():
    """Test getting worker stats successfully."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.stats.return_value = {
            "celery@worker1": {
                "pool": {"max-concurrency": 4, "processes": 4},
                "uptime": 3600,
            }
        }
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        result = await get_worker_stats("celery@worker1")

        assert "stats" in result
        assert result["stats"]["pool"]["max-concurrency"] == 4


@pytest.mark.asyncio
async def test_get_worker_stats_not_found():
    """Test getting stats for non-existent worker."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.stats.return_value = {}
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        result = await get_worker_stats("celery@worker1")

        assert "error" in result
        assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_shutdown_worker_success():
    """Test shutting down a worker successfully."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        result = await shutdown_worker("celery@worker1")

        assert result["status"] == "success"
        mock_app.control.shutdown.assert_called_once_with(destination=["celery@worker1"])


@pytest.mark.asyncio
async def test_shutdown_worker_error():
    """Test shutting down a worker when an error occurs."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_app.control.shutdown.side_effect = Exception("Shutdown failed")
        mock_get_app.return_value = mock_app

        result = await shutdown_worker("celery@worker1")

        assert "error" in result
        assert "Failed to shutdown worker" in result["error"]


@pytest.mark.asyncio
async def test_scale_worker_pool_grow():
    """Test growing worker pool."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        result = await scale_worker_pool("celery@worker1", 2)

        assert result["status"] == "success"
        assert result["delta"] == 2
        mock_app.control.pool_grow.assert_called_once_with(n=2, destination=["celery@worker1"])


@pytest.mark.asyncio
async def test_scale_worker_pool_shrink():
    """Test shrinking worker pool."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        result = await scale_worker_pool("celery@worker1", -1)

        assert result["status"] == "success"
        assert result["delta"] == -1
        mock_app.control.pool_shrink.assert_called_once_with(n=1, destination=["celery@worker1"])


@pytest.mark.asyncio
async def test_scale_worker_pool_zero_delta():
    """Test scaling with zero delta returns error."""
    result = await scale_worker_pool("celery@worker1", 0)

    assert "error" in result
    assert "non-zero" in result["error"]


@pytest.mark.asyncio
async def test_scale_worker_pool_error():
    """Test scaling worker pool when an error occurs."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_app.control.pool_grow.side_effect = Exception("Scale failed")
        mock_get_app.return_value = mock_app

        result = await scale_worker_pool("celery@worker1", 2)

        assert "error" in result
        assert "Failed to scale worker pool" in result["error"]


@pytest.mark.asyncio
async def test_get_active_tasks_success():
    """Test getting active tasks."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {
            "celery@worker1": [{"id": "task-1", "name": "myapp.tasks.task1"}]
        }
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        result = await get_active_tasks()

        assert "active_tasks" in result
        assert "celery@worker1" in result["active_tasks"]


@pytest.mark.asyncio
async def test_get_active_tasks_with_worker_filter():
    """Test getting active tasks for specific worker."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.destination.return_value = mock_inspect
        mock_inspect.active.return_value = {
            "celery@worker1": [{"id": "task-1", "name": "myapp.tasks.task1"}]
        }
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        result = await get_active_tasks("celery@worker1")

        assert "active_tasks" in result
        mock_inspect.destination.assert_called_once_with(["celery@worker1"])


@pytest.mark.asyncio
async def test_get_active_tasks_no_tasks():
    """Test getting active tasks when none are running."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = None
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        result = await get_active_tasks()

        assert result == {"active_tasks": {}}


@pytest.mark.asyncio
async def test_get_active_tasks_error():
    """Test getting active tasks when an error occurs."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_get_app.side_effect = Exception("Connection failed")

        result = await get_active_tasks()

        assert "error" in result
        assert "Failed to get active tasks" in result["error"]
