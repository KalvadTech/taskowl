"""Workflow automation CRUD functions for taskowl.

This module contains the core logic for managing workflow automations
(declarative trigger -> conditions -> actions definitions) that can be
used by both REST API endpoints and MCP tools.
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.database import async_session_maker
from taskowl.models import Automation, AutomationRun

logger = logging.getLogger(__name__)

_VALID_TRIGGERS = ("event", "periodic")
_VALID_EVENT_TYPES = (
    "task-sent",
    "task-received",
    "task-started",
    "task-succeeded",
    "task-failed",
    "task-revoked",
    "task-retried",
    "task-rejected",
    "worker-online",
    "worker-heartbeat",
    "worker-offline",
)


def _validate_automation(data: dict) -> str | None:
    """Validate an automation definition. Returns an error message or None."""
    trigger_type = data.get("trigger_type")
    if trigger_type not in _VALID_TRIGGERS:
        return f"trigger_type must be one of {list(_VALID_TRIGGERS)}"

    if trigger_type == "event":
        event_type = data.get("event_type")
        if not event_type:
            return "event_type is required for event triggers"
        if event_type not in _VALID_EVENT_TYPES:
            return f"event_type must be one of {list(_VALID_EVENT_TYPES)}"
    elif trigger_type == "periodic":
        schedule_seconds = data.get("schedule_seconds")
        if not isinstance(schedule_seconds, int) or schedule_seconds <= 0:
            return "schedule_seconds must be a positive integer for periodic triggers"

    cooldown = data.get("cooldown_seconds")
    if cooldown is not None and (not isinstance(cooldown, int) or cooldown < 0):
        return "cooldown_seconds must be a non-negative integer"

    max_runs = data.get("max_runs_per_window")
    window = data.get("window_seconds")
    if max_runs is not None and (not isinstance(max_runs, int) or max_runs <= 0):
        return "max_runs_per_window must be a positive integer"
    if max_runs is not None and (not isinstance(window, int) or window <= 0):
        return "window_seconds is required when max_runs_per_window is set"

    return None


def _serialize(automation: Automation) -> dict:
    """Convert an Automation model to a JSON-serializable dict."""
    return {
        "id": automation.id,
        "name": automation.name,
        "enabled": automation.enabled,
        "trigger_type": automation.trigger_type,
        "event_type": automation.event_type,
        "schedule_seconds": automation.schedule_seconds,
        "conditions": automation.conditions,
        "actions": automation.actions,
        "cooldown_seconds": automation.cooldown_seconds,
        "max_runs_per_window": automation.max_runs_per_window,
        "window_seconds": automation.window_seconds,
        "circuit_breaker": automation.circuit_breaker,
        "created_at": automation.created_at.isoformat() if automation.created_at else None,
        "updated_at": automation.updated_at.isoformat() if automation.updated_at else None,
    }


def _serialize_run(run: AutomationRun) -> dict:
    """Convert an AutomationRun model to a JSON-serializable dict."""
    return {
        "id": run.id,
        "automation_id": run.automation_id,
        "trigger": run.trigger,
        "matched": run.matched,
        "conditions_passed": run.conditions_passed,
        "actions_fired": run.actions_fired,
        "details": run.details,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


async def create_automation(
    data: dict,
    session: AsyncSession | None = None,
) -> dict:
    """Create a new automation definition.

    Args:
        data: Automation definition dict
        session: Optional database session (for testing)

    Returns:
        Dict with the created automation or an error
    """
    error = _validate_automation(data)
    if error:
        return {"error": error}
    if not data.get("name"):
        return {"error": "name is required"}

    async def _create(session: AsyncSession) -> dict:
        existing = await session.execute(select(Automation).where(Automation.name == data["name"]))
        if existing.scalar_one_or_none() is not None:
            return {"error": f"Automation with name '{data['name']}' already exists"}

        automation = Automation(
            name=data["name"],
            enabled=data.get("enabled", True),
            trigger_type=data["trigger_type"],
            event_type=data.get("event_type"),
            schedule_seconds=data.get("schedule_seconds"),
            conditions=data.get("conditions"),
            actions=data.get("actions"),
            cooldown_seconds=data.get("cooldown_seconds"),
            max_runs_per_window=data.get("max_runs_per_window"),
            window_seconds=data.get("window_seconds"),
            circuit_breaker=data.get("circuit_breaker"),
        )
        session.add(automation)
        await session.commit()
        await session.refresh(automation)
        return _serialize(automation)

    if session is None:
        async with async_session_maker() as db_session:
            return await _create(db_session)
    return await _create(session)


async def get_automation(
    automation_id: int,
    session: AsyncSession | None = None,
) -> dict:
    """Get an automation by id.

    Args:
        automation_id: ID of the automation
        session: Optional database session (for testing)

    Returns:
        Dict with the automation or an error
    """

    async def _get(session: AsyncSession) -> dict:
        result = await session.execute(select(Automation).where(Automation.id == automation_id))
        automation = result.scalar_one_or_none()
        if automation is None:
            return {"error": f"Automation not found: {automation_id}"}
        return _serialize(automation)

    if session is None:
        async with async_session_maker() as db_session:
            return await _get(db_session)
    return await _get(session)


async def list_automations(
    enabled: bool | None = None,
    session: AsyncSession | None = None,
) -> list[dict]:
    """List automations, optionally filtered by enabled state.

    Args:
        enabled: If set, filter by enabled/disabled
        session: Optional database session (for testing)

    Returns:
        List of automation dicts
    """

    async def _list(session: AsyncSession) -> list[dict]:
        query = select(Automation).order_by(Automation.id)
        if enabled is not None:
            query = query.where(Automation.enabled == enabled)
        result = await session.execute(query)
        return [_serialize(a) for a in result.scalars().all()]

    if session is None:
        async with async_session_maker() as db_session:
            return await _list(db_session)
    return await _list(session)


async def update_automation(
    automation_id: int,
    data: dict,
    session: AsyncSession | None = None,
) -> dict:
    """Update an automation definition.

    Args:
        automation_id: ID of the automation
        data: Fields to update
        session: Optional database session (for testing)

    Returns:
        Dict with the updated automation or an error
    """
    merged = {k: v for k, v in data.items() if v is not None}
    if not merged:
        return {"error": "No fields to update"}

    # Validate the merged definition (respect existing values for unset fields)
    async def _update(session: AsyncSession) -> dict:
        result = await session.execute(select(Automation).where(Automation.id == automation_id))
        automation = result.scalar_one_or_none()
        if automation is None:
            return {"error": f"Automation not found: {automation_id}"}

        current = _serialize(automation)
        merged_def = {**current, **merged}
        error = _validate_automation(merged_def)
        if error:
            return {"error": error}

        for field, value in merged.items():
            if field in ("created_at", "updated_at", "id"):
                continue
            setattr(automation, field, value)

        await session.commit()
        await session.refresh(automation)
        return _serialize(automation)

    if session is None:
        async with async_session_maker() as db_session:
            return await _update(db_session)
    return await _update(session)


async def delete_automation(
    automation_id: int,
    session: AsyncSession | None = None,
) -> dict:
    """Delete an automation and its run history.

    Args:
        automation_id: ID of the automation
        session: Optional database session (for testing)

    Returns:
        Dict with status or an error
    """

    async def _delete(session: AsyncSession) -> dict:
        result = await session.execute(select(Automation).where(Automation.id == automation_id))
        if result.scalar_one_or_none() is None:
            return {"error": f"Automation not found: {automation_id}"}
        await session.execute(delete(Automation).where(Automation.id == automation_id))
        await session.execute(
            delete(AutomationRun).where(AutomationRun.automation_id == automation_id)
        )
        await session.commit()
        return {"status": "success", "message": f"Automation {automation_id} deleted"}

    if session is None:
        async with async_session_maker() as db_session:
            return await _delete(db_session)
    return await _delete(session)


async def toggle_automation(
    automation_id: int,
    session: AsyncSession | None = None,
) -> dict:
    """Toggle an automation's enabled state.

    Args:
        automation_id: ID of the automation
        session: Optional database session (for testing)

    Returns:
        Dict with the updated automation or an error
    """

    async def _toggle(session: AsyncSession) -> dict:
        result = await session.execute(select(Automation).where(Automation.id == automation_id))
        automation = result.scalar_one_or_none()
        if automation is None:
            return {"error": f"Automation not found: {automation_id}"}
        automation.enabled = not automation.enabled
        await session.commit()
        await session.refresh(automation)
        return _serialize(automation)

    if session is None:
        async with async_session_maker() as db_session:
            return await _toggle(db_session)
    return await _toggle(session)


async def get_automation_status(
    automation_id: int,
    session: AsyncSession | None = None,
) -> dict:
    """Get an automation's status, including current circuit-breaker state.

    Args:
        automation_id: ID of the automation
        session: Optional database session (for testing)

    Returns:
        Dict with the automation plus its latest run and circuit state
    """

    async def _get(session: AsyncSession) -> dict:
        result = await session.execute(select(Automation).where(Automation.id == automation_id))
        automation = result.scalar_one_or_none()
        if automation is None:
            return {"error": f"Automation not found: {automation_id}"}

        runs = await list_automation_runs(automation_id, limit=1, session=session)
        latest_run = runs[0] if runs else None

        circuit_state = "closed"
        circuit_config = automation.circuit_breaker
        if (
            circuit_config
            and latest_run
            and (latest_run.get("details") or {}).get("skipped") == "circuit_open"
        ):
            circuit_state = "open"

        return {
            **_serialize(automation),
            "circuit_state": circuit_state,
            "last_run": latest_run,
        }

    if session is None:
        async with async_session_maker() as db_session:
            return await _get(db_session)
    return await _get(session)


async def list_automation_runs(
    automation_id: int | None = None,
    limit: int = 50,
    session: AsyncSession | None = None,
) -> list[dict]:
    """List automation runs, optionally filtered by automation id.

    Args:
        automation_id: If set, only runs for this automation
        limit: Max number of runs to return (default: 50)
        session: Optional database session (for testing)

    Returns:
        List of run dicts (newest first)
    """

    async def _list(session: AsyncSession) -> list[dict]:
        query = (
            select(AutomationRun)
            .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
            .limit(limit)
        )
        if automation_id is not None:
            query = query.where(AutomationRun.automation_id == automation_id)
        result = await session.execute(query)
        return [_serialize_run(r) for r in result.scalars().all()]

    if session is None:
        async with async_session_maker() as db_session:
            return await _list(db_session)
    return await _list(session)


async def seed_builtin_automations(session: AsyncSession | None = None) -> list[dict]:
    """Create the built-in alert automations from the legacy env-var settings.

    Idempotent: only creates an automation if one with that name does not
    already exist. Returns the list of newly created automations.

    These automations replicate the legacy ``ALERT_*`` behavior (task-failed,
    slow-task, worker-offline event, and the periodic stale-worker sweep) so
    the engine is the single alerting mechanism.

    Args:
        session: Optional database session (for testing)

    Returns:
        List of created automation dicts
    """
    from taskowl.config import settings

    webhook_url = settings.alert_webhook_url
    created: list[dict] = []

    async def _ensure(
        name: str,
        definition: dict,
        session: AsyncSession,
    ) -> None:
        existing = await session.execute(select(Automation).where(Automation.name == name))
        if existing.scalar_one_or_none() is not None:
            return
        automation = Automation(
            name=name,
            enabled=definition.get("enabled", True),
            trigger_type=definition["trigger_type"],
            event_type=definition.get("event_type"),
            schedule_seconds=definition.get("schedule_seconds"),
            conditions=definition.get("conditions"),
            actions=definition.get("actions"),
        )
        session.add(automation)
        await session.flush()
        created.append(_serialize(automation))

    async def _seed(session: AsyncSession) -> None:
        if not webhook_url:
            return

        if settings.alert_on_task_failed:
            await _ensure(
                "alert-task-failed",
                {
                    "trigger_type": "event",
                    "event_type": "task-failed",
                    "conditions": [],
                    "actions": [
                        {
                            "type": "slack_webhook",
                            "webhook_url": webhook_url,
                            "text": "Task failed",
                            "fields": {
                                "Task": "{event.name}",
                                "Task ID": "{event.uuid}",
                                "Worker": "{event.hostname}",
                                "Error": "{event.exception}",
                            },
                        }
                    ],
                },
                session,
            )

        if settings.alert_slow_task_seconds is not None:
            await _ensure(
                "alert-slow-task",
                {
                    "trigger_type": "event",
                    "event_type": "task-succeeded",
                    "conditions": [
                        {
                            "field": "runtime",
                            "op": "gt",
                            "value": settings.alert_slow_task_seconds,
                        }
                    ],
                    "actions": [
                        {
                            "type": "slack_webhook",
                            "webhook_url": webhook_url,
                            "text": "Slow task detected",
                            "fields": {
                                "Task": "{event.name}",
                                "Task ID": "{event.uuid}",
                                "Runtime (s)": "{event.runtime}",
                                "Worker": "{event.hostname}",
                            },
                        }
                    ],
                },
                session,
            )

        if settings.alert_on_worker_offline:
            await _ensure(
                "alert-worker-offline",
                {
                    "trigger_type": "event",
                    "event_type": "worker-offline",
                    "conditions": [],
                    "actions": [
                        {
                            "type": "slack_webhook",
                            "webhook_url": webhook_url,
                            "text": "Worker offline",
                            "fields": {"Worker": "{event.hostname}"},
                        }
                    ],
                },
                session,
            )
            await _ensure(
                "alert-worker-offline-sweep",
                {
                    "trigger_type": "periodic",
                    "schedule_seconds": settings.alert_worker_check_seconds,
                    "conditions": [],
                    "actions": [{"type": "check_workers_offline", "webhook_url": webhook_url}],
                },
                session,
            )

        await session.commit()

    if session is None:
        async with async_session_maker() as db_session:
            await _seed(db_session)
    else:
        await _seed(session)

    return created
