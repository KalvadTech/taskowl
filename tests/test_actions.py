"""Tests for task actions."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.actions import retry_task, revoke_task
from taskowl.models import TaskEvent


@pytest.mark.asyncio
async def test_revoke_task_success(db_session: AsyncSession):
    """Test successful task revocation."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Create a task in the database
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

    # Mock Celery control
    with patch("taskowl.actions._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app

        result = await revoke_task(str(task_id), terminate=False, session=db_session)

        assert result["status"] == "success"
        assert f"Task {task_id} has been revoked" in result["message"]
        assert result["terminated"] is False
        mock_app.control.revoke.assert_called_once_with(str(task_id), terminate=False)


@pytest.mark.asyncio
async def test_revoke_task_with_terminate(db_session: AsyncSession):
    """Test task revocation with terminate=True."""
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

        result = await revoke_task(str(task_id), terminate=True, session=db_session)

        assert result["status"] == "success"
        assert result["terminated"] is True
        mock_app.control.revoke.assert_called_once_with(str(task_id), terminate=True)


@pytest.mark.asyncio
async def test_revoke_task_not_found(db_session: AsyncSession):
    """Test revoking non-existent task."""
    task_id = uuid.uuid4()

    result = await revoke_task(str(task_id), session=db_session)

    assert "error" in result
    assert "Task not found" in result["error"]


@pytest.mark.asyncio
async def test_revoke_task_invalid_uuid(db_session: AsyncSession):
    """Test revoking with invalid UUID."""
    result = await revoke_task("invalid-uuid", session=db_session)

    assert "error" in result
    assert "Invalid task_id format" in result["error"]


@pytest.mark.asyncio
async def test_revoke_task_celery_error(db_session: AsyncSession):
    """Test revoking when Celery raises an error."""
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
        mock_app.control.revoke.side_effect = Exception("Connection failed")
        mock_get_app.return_value = mock_app

        result = await revoke_task(str(task_id), session=db_session)

        assert "error" in result
        assert "Failed to revoke task" in result["error"]


@pytest.mark.asyncio
async def test_retry_task_success(db_session: AsyncSession):
    """Test successful task retry."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Create a failed task in the database
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
            name="test_task",
            args={"arg1": "value1"},
            kwargs={"kwarg1": "value2"},
            queue="default",
        )
    )
    db_session.add(
        TaskEvent(
            event_type="failed",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
            exception="ValueError",
        )
    )
    await db_session.commit()

    # Mock Celery send_task
    with patch("taskowl.actions._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "new-task-id-123"
        mock_app.send_task.return_value = mock_result
        mock_get_app.return_value = mock_app

        result = await retry_task(str(task_id), session=db_session)

        assert result["status"] == "success"
        assert f"Task {task_id} has been retried" in result["message"]
        assert result["new_task_id"] == "new-task-id-123"
        mock_app.send_task.assert_called_once_with(
            "test_task",
            args={"arg1": "value1"},
            kwargs={"kwarg1": "value2"},
            queue="default",
        )


@pytest.mark.asyncio
async def test_retry_task_revoked_state(db_session: AsyncSession):
    """Test retrying a revoked task."""
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
            event_type="revoked",
            task_id=task_id,
            timestamp=now + timedelta(seconds=1),
            hostname="worker1@localhost",
        )
    )
    await db_session.commit()

    with patch("taskowl.actions._get_celery_app") as mock_get_app:
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "new-task-id-456"
        mock_app.send_task.return_value = mock_result
        mock_get_app.return_value = mock_app

        result = await retry_task(str(task_id), session=db_session)

        assert result["status"] == "success"
        assert result["new_task_id"] == "new-task-id-456"


@pytest.mark.asyncio
async def test_retry_task_wrong_state(db_session: AsyncSession):
    """Test retrying a task that's not failed/revoked."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Create a succeeded task
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

    result = await retry_task(str(task_id), session=db_session)

    assert "error" in result
    assert "succeeded" in result["error"]
    assert "Only failed or revoked tasks can be retried" in result["error"]


@pytest.mark.asyncio
async def test_retry_task_not_found(db_session: AsyncSession):
    """Test retrying non-existent task."""
    task_id = uuid.uuid4()

    result = await retry_task(str(task_id), session=db_session)

    assert "error" in result
    assert "Task not found" in result["error"]


@pytest.mark.asyncio
async def test_retry_task_invalid_uuid(db_session: AsyncSession):
    """Test retrying with invalid UUID."""
    result = await retry_task("invalid-uuid", session=db_session)

    assert "error" in result
    assert "Invalid task_id format" in result["error"]


@pytest.mark.asyncio
async def test_retry_task_missing_name(db_session: AsyncSession):
    """Test retrying a task without a name."""
    task_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Create a failed task without name
    db_session.add(
        TaskEvent(
            event_type="received",
            task_id=task_id,
            timestamp=now,
            hostname="worker1@localhost",
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

    result = await retry_task(str(task_id), session=db_session)

    assert "error" in result
    assert "task name not found" in result["error"]


@pytest.mark.asyncio
async def test_retry_task_celery_error(db_session: AsyncSession):
    """Test retrying when Celery raises an error."""
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
        mock_app.send_task.side_effect = Exception("Connection failed")
        mock_get_app.return_value = mock_app

        result = await retry_task(str(task_id), session=db_session)

        assert "error" in result
        assert "Failed to retry task" in result["error"]
