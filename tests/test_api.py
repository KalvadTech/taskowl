"""Tests for REST API endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

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
    assert data[0]["status"] == "heartbeat"
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
