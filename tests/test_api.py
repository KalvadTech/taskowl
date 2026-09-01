"""Tests for REST API endpoints."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.models import TaskEvent, WorkerEvent


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    """Test root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "taskowl"
    assert "version" in data
    assert "description" in data


@pytest.mark.asyncio
async def test_api_list_tasks_empty(client: AsyncClient):
    """Test GET /api/tasks with no data."""
    response = await client.get("/api/tasks")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_list_tasks_with_data(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks with task data."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )
    await db_session.commit()

    response = await client.get("/api/tasks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(task_id)
    assert data[0]["state"] == "succeeded"


@pytest.mark.asyncio
async def test_api_list_tasks_with_filters(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks with query parameters."""
    task1_id = uuid.uuid4()
    task2_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task1_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="task_a",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="failed",
            task_id=task2_id,
            timestamp=now,
            hostname="worker2@localhost",
            name="task_b",
        )
    )
    await db_session.commit()

    # Filter by state
    response = await client.get("/api/tasks?state=succeeded")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(task1_id)

    # Filter by name
    response = await client.get("/api/tasks?name=task_b")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "task_b"

    # Filter by worker
    response = await client.get("/api/tasks?worker=worker1@localhost")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["worker"] == "worker1@localhost"


@pytest.mark.asyncio
async def test_api_list_tasks_search_offset_sort(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks with search, offset, and sort_by params."""
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now + timedelta(seconds=2),
            hostname="worker1@localhost",
            name="zeta_task",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
            name="alpha_task",
        )
    )
    await db_session.commit()

    # search partial match
    response = await client.get("/api/tasks?search=TASK")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # search no match
    response = await client.get("/api/tasks?search=nope")
    assert response.status_code == 200
    assert response.json() == []

    # sort_by name ascending
    response = await client.get("/api/tasks?sort_by=name")
    assert response.status_code == 200
    data = response.json()
    assert [t["name"] for t in data] == ["alpha_task", "zeta_task"]

    # invalid sort_by -> 400
    response = await client.get("/api/tasks?sort_by=bogus")
    assert response.status_code == 400

    # offset skips newest first (default timestamp desc)
    response = await client.get("/api/tasks?offset=1")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_api_list_task_types(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks/types returns distinct names with counts."""
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now,
            hostname="worker1@localhost",
            name="app.tasks.alpha",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now,
            hostname="worker1@localhost",
            name="app.tasks.alpha",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=uuid.uuid4(),
            timestamp=now,
            hostname="worker1@localhost",
            name="app.tasks.beta",
        )
    )
    await db_session.commit()

    response = await client.get("/api/tasks/types")
    assert response.status_code == 200
    data = response.json()
    by_name = {t["name"]: t["count"] for t in data}
    assert by_name == {"app.tasks.alpha": 2, "app.tasks.beta": 1}


@pytest.mark.asyncio
async def test_api_list_task_types_empty(client: AsyncClient):
    """Test GET /api/tasks/types with no data."""
    response = await client.get("/api/tasks/types")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_get_task_summary_empty(client: AsyncClient):
    """Test GET /api/tasks/summary with no data."""
    response = await client.get("/api/tasks/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tasks"] == 0
    assert data["by_state"] == {}
    assert data["avg_runtime_seconds"] is None


@pytest.mark.asyncio
async def test_api_get_task_summary_with_data(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks/summary with task data."""
    now = datetime.now(UTC)

    for _ in range(3):
        db_session.add(
            TaskEvent(
                event_type="succeeded",
                task_id=uuid.uuid4(),
                timestamp=now,
                hostname="worker1@localhost",
                runtime=2.0,
            )
        )
    await db_session.commit()

    response = await client.get("/api/tasks/summary?hours=1")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tasks"] == 3
    assert data["by_state"]["succeeded"] == 3
    assert data["avg_runtime_seconds"] == 2.0


@pytest.mark.asyncio
async def test_api_get_task_success(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks/{task_id} with valid task."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
            runtime=1.5,
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(task_id)
    assert data["state"] == "succeeded"
    assert data["name"] == "test_task"
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_api_get_task_not_found(client: AsyncClient):
    """Test GET /api/tasks/{task_id} with non-existent task."""
    task_id = uuid.uuid4()
    response = await client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Task not found" in data["detail"]


@pytest.mark.asyncio
async def test_api_get_task_invalid_uuid(client: AsyncClient):
    """Test GET /api/tasks/{task_id} with invalid UUID."""
    response = await client.get("/api/tasks/invalid-uuid")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Invalid task_id format" in data["detail"]


@pytest.mark.asyncio
async def test_api_get_task_timeline_success(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks/{task_id}/timeline with valid task."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )

    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now + timedelta(seconds=2),
            hostname="worker1@localhost",
            runtime=1.5,
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/tasks/{task_id}/timeline")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["event_type"] == "received"
    assert data[1]["event_type"] == "started"
    assert data[2]["event_type"] == "succeeded"
    assert data[2]["details"]["runtime"] == 1.5


@pytest.mark.asyncio
async def test_api_get_task_timeline_not_found(client: AsyncClient):
    """Test GET /api/tasks/{task_id}/timeline with non-existent task."""
    task_id = uuid.uuid4()
    response = await client.get(f"/api/tasks/{task_id}/timeline")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Task not found" in data["detail"]


@pytest.mark.asyncio
async def test_api_get_task_timeline_invalid_uuid(client: AsyncClient):
    """Test GET /api/tasks/{task_id}/timeline with invalid UUID."""
    response = await client.get("/api/tasks/invalid-uuid/timeline")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Invalid task_id format" in data["detail"]


@pytest.mark.asyncio
async def test_api_get_workers_empty(client: AsyncClient):
    """Test GET /api/workers with no data."""
    response = await client.get("/api/workers")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_get_workers_with_data(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/workers with worker data."""
    now = datetime.now(UTC)

    db_session.add(
        WorkerEvent(
            event_type="online",
            hostname="worker1@localhost",
            timestamp=now,
            sw_ident="py-celery",
            sw_ver="5.3.0",
        )
    )

    db_session.add(
        WorkerEvent(
            event_type="heartbeat",
            hostname="worker1@localhost",
            timestamp=now + timedelta(seconds=10),
            active=2,
            processed=100,
        )
    )
    await db_session.commit()

    response = await client.get("/api/workers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["hostname"] == "worker1@localhost"
    assert data[0]["status"] == "online"
    assert data[0]["last_event"] == "heartbeat"
    assert data[0]["active"] == 2
    assert data[0]["processed"] == 100


# Authentication tests


@pytest.mark.asyncio
async def test_api_auth_missing_key(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """Test API returns 401 when API_KEY is set but no auth header provided."""
    monkeypatch.setenv("API_KEY", "test-secret-key")

    # Reload settings to pick up the new env var
    import importlib

    from taskowl import auth, config

    importlib.reload(config)
    importlib.reload(auth)

    from httpx import ASGITransport

    from taskowl.database import get_db
    from taskowl.main import app

    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await test_client.get("/api/tasks")
            assert response.status_code == 401
            assert "Missing authentication" in response.json()["detail"]
    finally:
        # Clean up
        app.dependency_overrides.clear()
        monkeypatch.delenv("API_KEY")
        importlib.reload(config)
        importlib.reload(auth)


@pytest.mark.asyncio
async def test_api_auth_wrong_key(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """Test API returns 401 when wrong API key is provided."""
    monkeypatch.setenv("API_KEY", "test-secret-key")

    import importlib

    from taskowl import auth, config

    importlib.reload(config)
    importlib.reload(auth)

    from httpx import ASGITransport

    from taskowl.database import get_db
    from taskowl.main import app

    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await test_client.get(
                "/api/tasks", headers={"Authorization": "Bearer wrong-key"}
            )
            assert response.status_code == 401
            assert "Invalid API key" in response.json()["detail"]
    finally:
        # Clean up
        app.dependency_overrides.clear()
        monkeypatch.delenv("API_KEY")
        importlib.reload(config)
        importlib.reload(auth)


@pytest.mark.asyncio
async def test_api_auth_correct_key(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """Test API returns 200 when correct API key is provided."""
    monkeypatch.setenv("API_KEY", "test-secret-key")

    import importlib

    from taskowl import auth, config

    importlib.reload(config)
    importlib.reload(auth)

    from httpx import ASGITransport

    from taskowl.database import get_db
    from taskowl.main import app

    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await test_client.get(
                "/api/tasks", headers={"Authorization": "Bearer test-secret-key"}
            )
            assert response.status_code == 200
    finally:
        # Clean up
        app.dependency_overrides.clear()
        monkeypatch.delenv("API_KEY")
        importlib.reload(config)
        importlib.reload(auth)


@pytest.mark.asyncio
async def test_api_auth_empty_string(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """Test API works without auth when API_KEY is set to empty string."""
    monkeypatch.setenv("API_KEY", "")

    import importlib

    from taskowl import auth, config

    importlib.reload(config)
    importlib.reload(auth)

    from httpx import ASGITransport

    from taskowl.database import get_db
    from taskowl.main import app

    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await test_client.get("/api/tasks")
            assert response.status_code == 200
    finally:
        # Clean up
        app.dependency_overrides.clear()
        monkeypatch.delenv("API_KEY", raising=False)
        importlib.reload(config)
        importlib.reload(auth)


@pytest.mark.asyncio
async def test_api_auth_not_configured(client: AsyncClient):
    """Test API works without auth when API_KEY is not set."""
    # API_KEY should not be set in test environment
    response = await client.get("/api/tasks")
    assert response.status_code == 200


# Task action endpoint tests


@pytest.mark.asyncio
async def test_api_revoke_task_success(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/tasks/{task_id}/revoke with valid task."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )
    await db_session.commit()

    with patch("taskowl.actions._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        response = await client.post(f"/api/tasks/{task_id}/revoke")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "has been revoked" in data["message"]


@pytest.mark.asyncio
async def test_api_revoke_task_with_terminate(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/tasks/{task_id}/revoke with terminate=true."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    with patch("taskowl.actions._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        response = await client.post(f"/api/tasks/{task_id}/revoke?terminate=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["terminated"] is True


@pytest.mark.asyncio
async def test_api_revoke_task_not_found(client: AsyncClient):
    """Test POST /api/tasks/{task_id}/revoke with non-existent task."""
    task_id = uuid.uuid4()
    response = await client.post(f"/api/tasks/{task_id}/revoke")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Task not found" in data["detail"]


@pytest.mark.asyncio
async def test_api_retry_task_success(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/tasks/{task_id}/retry with valid failed task."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="failed",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    with patch("taskowl.actions._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "new-task-id-123"
        mock_app.send_task.return_value = mock_result
        mock_get_app.return_value = mock_app

        response = await client.post(f"/api/tasks/{task_id}/retry")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "has been retried" in data["message"]
        assert data["new_task_id"] == "new-task-id-123"


@pytest.mark.asyncio
async def test_api_retry_task_wrong_state(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/tasks/{task_id}/retry with non-failed task."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    response = await client.post(f"/api/tasks/{task_id}/retry")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "succeeded" in data["detail"]


# Worker management endpoint tests


@pytest.mark.asyncio
async def test_api_list_workers(client: AsyncClient):
    """Test GET /api/workers/list."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {"celery@worker1": {"ok": "pong"}}
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        response = await client.get("/api/workers/list")
        assert response.status_code == 200
        data = response.json()
        assert "workers" in data


@pytest.mark.asyncio
async def test_api_get_worker_stats(client: AsyncClient):
    """Test GET /api/workers/{worker_name}/stats."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.stats.return_value = {"celery@worker1": {"pool": {"max-concurrency": 4}}}
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        response = await client.get("/api/workers/celery@worker1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data


@pytest.mark.asyncio
async def test_api_get_worker_stats_not_found(client: AsyncClient):
    """Test GET /api/workers/{worker_name}/stats with non-existent worker."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.stats.return_value = {}
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        response = await client.get("/api/workers/celery@worker1/stats")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


@pytest.mark.asyncio
async def test_api_shutdown_worker(client: AsyncClient):
    """Test POST /api/workers/{worker_name}/shutdown."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        response = await client.post("/api/workers/celery@worker1/shutdown")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


@pytest.mark.asyncio
async def test_api_scale_worker_pool(client: AsyncClient):
    """Test POST /api/workers/{worker_name}/scale."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        response = await client.post("/api/workers/celery@worker1/scale?delta=2")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["delta"] == 2


@pytest.mark.asyncio
async def test_api_scale_worker_pool_zero_delta(client: AsyncClient):
    """Test POST /api/workers/{worker_name}/scale with zero delta."""
    response = await client.post("/api/workers/celery@worker1/scale?delta=0")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_api_get_active_tasks(client: AsyncClient):
    """Test GET /api/workers/active-tasks."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {
            "celery@worker1": [{"id": "task-1", "name": "myapp.tasks.task1"}]
        }
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        response = await client.get("/api/workers/active-tasks")
        assert response.status_code == 200
        data = response.json()
        assert "active_tasks" in data


@pytest.mark.asyncio
async def test_api_get_active_tasks_with_worker_filter(client: AsyncClient):
    """Test GET /api/workers/active-tasks with worker filter."""
    with patch("taskowl.workers._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.destination.return_value = mock_inspect
        mock_inspect.active.return_value = {
            "celery@worker1": [{"id": "task-1", "name": "myapp.tasks.task1"}]
        }
        mock_app.control.inspect.return_value = mock_inspect
        mock_get_app.return_value = mock_app

        response = await client.get("/api/workers/active-tasks?worker_name=celery@worker1")
        assert response.status_code == 200
        data = response.json()
        assert "active_tasks" in data


@pytest.mark.asyncio
async def test_api_list_orphaned_tasks_empty(client: AsyncClient):
    """Test GET /api/tasks/orphaned with no orphaned tasks."""
    response = await client.get("/api/tasks/orphaned")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_list_orphaned_tasks_with_data(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks/orphaned with an orphaned task."""
    now = datetime.now(UTC)
    task_id = uuid.uuid4()

    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now - timedelta(seconds=300),
            hostname="worker1@localhost",
        )
    )
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    await db_session.commit()

    response = await client.get("/api/tasks/orphaned")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(task_id)
    assert data[0]["state"] == "orphaned"


@pytest.mark.asyncio
async def test_api_get_task_reports_orphaned(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks/{task_id} reports orphaned flag."""
    now = datetime.now(UTC)
    task_id = uuid.uuid4()

    db_session.add(
        TaskEvent(
            event_type="started",
            task_id=task_id,
            timestamp=now - timedelta(seconds=300),
            hostname="worker1@localhost",
        )
    )
    db_session.add(
        WorkerEvent(
            event_type="offline",
            hostname="worker1@localhost",
            timestamp=now - timedelta(seconds=120),
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["orphaned"] is True


@pytest.mark.asyncio
async def test_api_get_task_chain(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/tasks/{task_id}/chain."""
    root_id = uuid.uuid4()
    retry_1 = uuid.uuid4()
    now = datetime.now(UTC)

    for tid, parent in [(root_id, None), (retry_1, root_id)]:
        db_session.add(
            TaskEvent(
                event_type="started",
                task_id=tid,
                timestamp=now,
                hostname="worker1@localhost",
                root_id=root_id,
                parent_id=parent,
            )
        )
    await db_session.commit()

    response = await client.get(f"/api/tasks/{root_id}/chain")
    assert response.status_code == 200
    data = response.json()
    assert data["root_id"] == str(root_id)
    assert len(data["chain"]) == 2


@pytest.mark.asyncio
async def test_api_get_task_chain_not_found(client: AsyncClient):
    """Test GET /api/tasks/{task_id}/chain with invalid UUID."""
    response = await client.get("/api/tasks/invalid-uuid/chain")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_get_task_includes_chain_fields(client: AsyncClient, db_session: AsyncSession):
    """Test get_task includes root_id and parent_id."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
            root_id=task_id,
        )
    )
    db_session.add(
        TaskEvent(
            event_type="succeeded",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["root_id"] == str(task_id)
