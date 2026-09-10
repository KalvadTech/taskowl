"""Workflow automation evaluation engine.

Loads enabled automations and evaluates them against incoming Celery
events: trigger matching, condition evaluation, and action dispatch.
Every evaluation is recorded in the append-only ``automation_runs`` log.
"""

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.automations import _serialize
from taskowl.database import async_session_maker
from taskowl.models import Automation, AutomationRun

logger = logging.getLogger(__name__)

# Fields that are safe to store in the run audit log. Args/kwargs/results
# and tracebacks are deliberately excluded (metadata-only, like alerts).
_SAFE_FIELDS = (
    "type",
    "uuid",
    "hostname",
    "name",
    "runtime",
    "exception",
    "retries",
    "queue",
    "pid",
    "root_id",
    "parent_id",
)

_SUPPORTED_OPS = (
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "matches",
    "in",
    "exists",
)


def _resolve_field(event: dict, field: str) -> Any:
    """Resolve a (possibly dotted) field path against an event dict."""
    value: Any = event
    for part in field.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def evaluate_condition(event: dict, condition: dict) -> bool:
    """Evaluate a single condition ``{field, op, value}`` against an event."""
    field = condition.get("field")
    op = condition.get("op")
    value = condition.get("value")

    if not field or op not in _SUPPORTED_OPS:
        logger.warning("Invalid condition: %s", condition)
        return False

    actual = _resolve_field(event, field)

    if op == "exists":
        return actual is not None
    if op == "eq":
        return actual == value
    if op == "neq":
        return actual != value
    if op == "gt":
        return _safe_compare(actual, value) and actual > value
    if op == "gte":
        return _safe_compare(actual, value) and actual >= value
    if op == "lt":
        return _safe_compare(actual, value) and actual < value
    if op == "lte":
        return _safe_compare(actual, value) and actual <= value
    if op == "contains":
        if isinstance(actual, str) and isinstance(value, str):
            return value in actual
        if isinstance(actual, (list, dict)):
            return value in actual
        return False
    if op == "matches":
        return isinstance(value, str) and bool(re.search(value, str(actual or "")))
    if op == "in":
        return isinstance(value, (list, tuple)) and actual in value
    return False


def _safe_compare(actual: Any, value: Any) -> bool:
    """Return True if the two values are comparable (same numeric-ish type)."""
    if actual is None or value is None:
        return False
    if isinstance(actual, (int, float)) and isinstance(value, (int, float)):
        return True
    return type(actual) is type(value)


def _safe_snapshot(event: dict) -> dict:
    """Build a metadata-only snapshot of an event for the audit log."""
    return {field: event[field] for field in _SAFE_FIELDS if field in event}


class WorkflowEngine:
    """Evaluates Celery events against automations and records runs."""

    async def evaluate_event(
        self,
        event_type: str,
        event: dict,
        session: AsyncSession | None = None,
    ) -> None:
        """Evaluate an incoming event against all enabled event automations.

        Args:
            event_type: Celery event type (e.g. 'task-failed')
            event: The event payload dict
            session: Optional database session (for testing)
        """
        if session is None:
            async with async_session_maker() as db_session:
                await self._evaluate_event(db_session, event_type, event)
        else:
            await self._evaluate_event(session, event_type, event)

    async def _evaluate_event(
        self,
        session: AsyncSession,
        event_type: str,
        event: dict,
    ) -> None:
        """Internal implementation of evaluate_event."""
        result = await session.execute(
            select(Automation).where(
                Automation.enabled.is_(True),
                Automation.trigger_type == "event",
                Automation.event_type == event_type,
            )
        )
        automations = result.scalars().all()

        for automation in automations:
            conditions = automation.conditions or []
            conditions_passed = all(
                evaluate_condition(event, condition) for condition in conditions
            )

            actions_fired = None
            if conditions_passed:
                actions_fired = await self._dispatch_actions(automation, event, session)

            session.add(
                AutomationRun(
                    automation_id=automation.id,
                    trigger=event_type,
                    matched=True,
                    conditions_passed=conditions_passed,
                    actions_fired=actions_fired,
                    details={
                        "event_type": event_type,
                        "event": _safe_snapshot(event),
                        "automation": _serialize(automation),
                    },
                )
            )

        await session.commit()

    async def _dispatch_actions(
        self,
        automation: Automation,
        event: dict,
        session: AsyncSession,
    ) -> list[dict]:
        """Dispatch an automation's actions. Returns a list of fired actions."""
        fired = []
        for action in automation.actions or []:
            action_type = action.get("type")
            try:
                if action_type == "log":
                    self._fire_log(automation, event, action)
                    fired.append({"type": "log"})
                else:
                    logger.warning(
                        "Unsupported action type %r for automation %s (arrives in a later phase)",
                        action_type,
                        automation.name,
                    )
            except Exception:
                logger.exception("Action %r failed for automation %s", action_type, automation.name)
                fired.append({"type": action_type, "error": "action failed"})
        return fired

    @staticmethod
    def _fire_log(automation: Automation, event: dict, action: dict) -> None:
        """Fire a 'log' action: write a message to the application log."""
        level = (action.get("level") or "info").upper()
        message = action.get("message") or (
            f"Automation '{automation.name}' fired on {event.get('type')}"
        )
        logger.log(getattr(logging, level, logging.INFO), message)
