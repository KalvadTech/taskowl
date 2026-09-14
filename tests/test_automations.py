"""Tests for workflow automation CRUD functions."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.automations import (
    create_automation,
    delete_automation,
    get_automation,
    get_automation_status,
    list_automation_runs,
    list_automations,
    seed_builtin_automations,
    toggle_automation,
    update_automation,
)
from taskowl.models import AutomationRun


@pytest.mark.asyncio
async def test_create_automation_event(db_session: AsyncSession):
    """Test creating an event-triggered automation."""
    result = await create_automation(
        {
            "name": "alert-on-failure",
            "trigger_type": "event",
            "event_type": "task-failed",
            "conditions": [{"field": "name", "op": "eq", "value": "payments.charge"}],
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    assert "error" not in result
    assert result["name"] == "alert-on-failure"
    assert result["trigger_type"] == "event"
    assert result["event_type"] == "task-failed"
    assert result["enabled"] is True


@pytest.mark.asyncio
async def test_create_automation_periodic(db_session: AsyncSession):
    """Test creating a periodic automation."""
    result = await create_automation(
        {
            "name": "stale-worker-check",
            "trigger_type": "periodic",
            "schedule_seconds": 30,
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    assert "error" not in result
    assert result["trigger_type"] == "periodic"
    assert result["schedule_seconds"] == 30


@pytest.mark.asyncio
async def test_create_automation_duplicate_name(db_session: AsyncSession):
    """Test creating an automation with a duplicate name."""
    await create_automation(
        {"name": "dup", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    result = await create_automation(
        {"name": "dup", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )

    assert "error" in result
    assert "already exists" in result["error"]


@pytest.mark.asyncio
async def test_create_automation_missing_name(db_session: AsyncSession):
    """Test creating an automation without a name."""
    result = await create_automation(
        {"trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    assert "error" in result
    assert "name is required" in result["error"]


@pytest.mark.asyncio
async def test_create_automation_invalid_trigger(db_session: AsyncSession):
    """Test creating an automation with an invalid trigger type."""
    result = await create_automation(
        {"name": "bad", "trigger_type": "cron", "event_type": "task-failed"},
        session=db_session,
    )
    assert "error" in result
    assert "trigger_type" in result["error"]


@pytest.mark.asyncio
async def test_create_automation_event_missing_type(db_session: AsyncSession):
    """Test creating an event automation without an event type."""
    result = await create_automation(
        {"name": "bad", "trigger_type": "event"},
        session=db_session,
    )
    assert "error" in result
    assert "event_type is required" in result["error"]


@pytest.mark.asyncio
async def test_create_automation_periodic_bad_schedule(db_session: AsyncSession):
    """Test creating a periodic automation with a bad schedule."""
    result = await create_automation(
        {"name": "bad", "trigger_type": "periodic", "schedule_seconds": 0},
        session=db_session,
    )
    assert "error" in result
    assert "schedule_seconds" in result["error"]


@pytest.mark.asyncio
async def test_get_automation(db_session: AsyncSession):
    """Test getting an automation by id."""
    created = await create_automation(
        {"name": "getme", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    result = await get_automation(created["id"], session=db_session)
    assert result["id"] == created["id"]
    assert result["name"] == "getme"


@pytest.mark.asyncio
async def test_get_automation_not_found(db_session: AsyncSession):
    """Test getting a non-existent automation."""
    result = await get_automation(999, session=db_session)
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_list_automations(db_session: AsyncSession):
    """Test listing automations."""
    await create_automation(
        {"name": "a", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    await create_automation(
        {"name": "b", "trigger_type": "periodic", "schedule_seconds": 30},
        session=db_session,
    )
    result = await list_automations(session=db_session)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_automations_filter_enabled(db_session: AsyncSession):
    """Test listing automations filtered by enabled state."""
    a = await create_automation(
        {"name": "a", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    await toggle_automation(a["id"], session=db_session)

    result = await list_automations(enabled=True, session=db_session)
    assert all(item["enabled"] for item in result)
    assert len(result) == 0

    result = await list_automations(enabled=False, session=db_session)
    assert len(result) == 1
    assert result[0]["name"] == "a"


@pytest.mark.asyncio
async def test_update_automation(db_session: AsyncSession):
    """Test updating an automation."""
    created = await create_automation(
        {"name": "update-me", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    result = await update_automation(
        created["id"],
        {"enabled": False, "cooldown_seconds": 60},
        session=db_session,
    )
    assert result["enabled"] is False
    assert result["cooldown_seconds"] == 60


@pytest.mark.asyncio
async def test_update_automation_not_found(db_session: AsyncSession):
    """Test updating a non-existent automation."""
    result = await update_automation(999, {"enabled": False}, session=db_session)
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_delete_automation(db_session: AsyncSession):
    """Test deleting an automation."""
    created = await create_automation(
        {"name": "delete-me", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    db_session.add(AutomationRun(automation_id=created["id"], trigger="task-failed", matched=True))
    await db_session.commit()

    result = await delete_automation(created["id"], session=db_session)
    assert result["status"] == "success"

    remaining = await list_automations(session=db_session)
    assert remaining == []
    runs = await list_automation_runs(created["id"], session=db_session)
    assert runs == []


@pytest.mark.asyncio
async def test_toggle_automation(db_session: AsyncSession):
    """Test toggling an automation's enabled state."""
    created = await create_automation(
        {"name": "toggle-me", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    result = await toggle_automation(created["id"], session=db_session)
    assert result["enabled"] is False
    result = await toggle_automation(created["id"], session=db_session)
    assert result["enabled"] is True


@pytest.mark.asyncio
async def test_list_automation_runs(db_session: AsyncSession):
    """Test listing automation runs."""
    created = await create_automation(
        {"name": "runs", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    db_session.add_all(
        [
            AutomationRun(automation_id=created["id"], trigger="task-failed", matched=True),
            AutomationRun(automation_id=created["id"], trigger="task-failed", matched=False),
        ]
    )
    await db_session.commit()

    runs = await list_automation_runs(created["id"], session=db_session)
    assert len(runs) == 2
    assert runs[0]["matched"] is False  # newest first


@pytest.mark.asyncio
async def test_list_automation_runs_no_runs(db_session: AsyncSession):
    """Test listing automation runs when there are none."""
    created = await create_automation(
        {"name": "no-runs", "trigger_type": "event", "event_type": "task-failed"},
        session=db_session,
    )
    runs = await list_automation_runs(created["id"], session=db_session)
    assert runs == []


@pytest.mark.asyncio
async def test_seed_builtin_automations(db_session: AsyncSession):
    """Test seeding built-in alert automations from env settings."""
    with patch(
        "taskowl.config.settings",
        alert_webhook_url="http://hooks.test/x",
        alert_on_task_failed=True,
        alert_on_worker_offline=True,
        alert_slow_task_seconds=30.0,
        alert_worker_check_seconds=60,
    ):
        created = await seed_builtin_automations(session=db_session)

    names = {a["name"] for a in created}
    assert {
        "alert-task-failed",
        "alert-slow-task",
        "alert-worker-offline",
        "alert-worker-offline-sweep",
    } <= names

    # Idempotent: seeding again creates nothing new
    with patch(
        "taskowl.config.settings",
        alert_webhook_url="http://hooks.test/x",
        alert_on_task_failed=True,
        alert_on_worker_offline=True,
        alert_slow_task_seconds=30.0,
        alert_worker_check_seconds=60,
    ):
        second = await seed_builtin_automations(session=db_session)
    assert second == []


@pytest.mark.asyncio
async def test_seed_builtin_automations_no_webhook(db_session: AsyncSession):
    """Test seeding does nothing without a webhook URL."""
    with patch("taskowl.config.settings", alert_webhook_url=None):
        created = await seed_builtin_automations(session=db_session)
    assert created == []


@pytest.mark.asyncio
async def test_get_automation_status_circuit_open(db_session: AsyncSession):
    """Test automation status reports circuit state from the latest run."""
    created = await create_automation(
        {
            "name": "status-demo",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "circuit_breaker": {"failure_threshold": 2, "window_seconds": 60},
        },
        session=db_session,
    )
    db_session.add(
        AutomationRun(
            automation_id=created["id"],
            trigger="task-failed",
            matched=True,
            actions_fired=None,
            details={"skipped": "circuit_open"},
        )
    )
    await db_session.commit()

    result = await get_automation_status(created["id"], session=db_session)
    assert result["circuit_state"] == "open"
    assert result["last_run"]["details"]["skipped"] == "circuit_open"


@pytest.mark.asyncio
async def test_get_automation_status_circuit_closed(db_session: AsyncSession):
    """Test automation status reports closed circuit without a skip."""
    created = await create_automation(
        {
            "name": "status-closed",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "circuit_breaker": {"failure_threshold": 2, "window_seconds": 60},
        },
        session=db_session,
    )
    db_session.add(
        AutomationRun(
            automation_id=created["id"],
            trigger="task-failed",
            matched=True,
            actions_fired=[{"type": "log"}],
        )
    )
    await db_session.commit()

    result = await get_automation_status(created["id"], session=db_session)
    assert result["circuit_state"] == "closed"


@pytest.mark.asyncio
async def test_get_automation_status_not_found(db_session: AsyncSession):
    """Test automation status for a non-existent automation."""
    result = await get_automation_status(999, session=db_session)
    assert "error" in result
    assert "not found" in result["error"]
