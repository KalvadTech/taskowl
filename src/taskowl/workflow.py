"""Workflow automation evaluation engine.

Loads enabled automations and evaluates them against incoming Celery
events: trigger matching, condition evaluation, and action dispatch.
Every evaluation is recorded in the append-only ``automation_runs`` log.
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.actions import execute_task, retry_task, revoke_task
from taskowl.alerting import WebhookClient
from taskowl.automations import _serialize
from taskowl.config import settings
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
        now = datetime.now(UTC)

        for automation in automations:
            conditions = automation.conditions or []
            conditions_passed = all(
                evaluate_condition(event, condition) for condition in conditions
            )

            actions_fired = None
            skipped = None
            if conditions_passed:
                skipped = await self._check_rate_limits(automation, now, session)
                if skipped is None:
                    actions_fired = await self._dispatch_actions(automation, event, session)

            details: dict = {
                "event_type": event_type,
                "event": _safe_snapshot(event),
                "automation": _serialize(automation),
            }
            if skipped is not None:
                details["skipped"] = skipped

            session.add(
                AutomationRun(
                    automation_id=automation.id,
                    trigger=event_type,
                    matched=True,
                    conditions_passed=conditions_passed,
                    actions_fired=actions_fired,
                    details=details,
                )
            )

        await session.commit()

    async def _check_rate_limits(
        self,
        automation: Automation,
        now: datetime,
        session: AsyncSession,
    ) -> str | None:
        """Enforce cooldown and max-runs-per-window. Returns a skip reason or None."""
        cooldown = automation.cooldown_seconds
        if cooldown is not None:
            last_fire = await self._last_fire_time(automation.id, session)
            if last_fire is not None and now - last_fire < timedelta(seconds=cooldown):
                return "cooldown"

        max_runs = automation.max_runs_per_window
        window = automation.window_seconds
        if max_runs is not None and window is not None:
            fired = await self._count_fired_in_window(automation.id, window, now, session)
            if fired >= max_runs:
                return "rate_limited"

        return None

    @staticmethod
    async def _last_fire_time(automation_id: int, session: AsyncSession) -> datetime | None:
        """Return the timestamp of the last run that fired actions (or None)."""
        result = await session.execute(
            select(AutomationRun.created_at)
            .where(
                AutomationRun.automation_id == automation_id,
                AutomationRun.actions_fired.isnot(None),
            )
            .order_by(AutomationRun.created_at.desc())
            .limit(1)
        )
        ts = result.scalar_one_or_none()
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts

    @staticmethod
    async def _count_fired_in_window(
        automation_id: int,
        window_seconds: int,
        now: datetime,
        session: AsyncSession,
    ) -> int:
        """Count runs that fired actions within the given window."""
        since = now - timedelta(seconds=window_seconds)
        result = await session.execute(
            select(func.count())
            .select_from(AutomationRun)
            .where(
                AutomationRun.automation_id == automation_id,
                AutomationRun.actions_fired.isnot(None),
                AutomationRun.created_at >= since,
            )
        )
        return result.scalar_one() or 0

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
                elif action_type == "slack_webhook":
                    await self._fire_slack_webhook(automation, event, action)
                    fired.append({"type": "slack_webhook"})
                elif action_type == "webhook":
                    await self._fire_webhook(automation, event, action)
                    fired.append({"type": "webhook"})
                elif action_type == "retry_task":
                    result = await self._fire_retry_task(event, action, session)
                    fired.append({"type": "retry_task", **result})
                elif action_type == "execute_task":
                    result = await self._fire_execute_task(event, action)
                    fired.append({"type": "execute_task", **result})
                elif action_type == "revoke_task":
                    result = await self._fire_revoke_task(event, action, session)
                    fired.append({"type": "revoke_task", **result})
                else:
                    logger.warning(
                        "Unsupported action type %r for automation %s",
                        action_type,
                        automation.name,
                    )
            except Exception:
                logger.exception("Action %r failed for automation %s", action_type, automation.name)
                fired.append({"type": action_type, "error": "action failed"})
        return fired

    @staticmethod
    def _interpolate(value: Any, event: dict) -> Any:
        """Substitute ``{event.field}`` references in action params with event values."""
        if isinstance(value, str):

            def _sub(match: re.Match) -> str:
                field = match.group(1)
                resolved = _resolve_field(event, field)
                return str(resolved) if resolved is not None else match.group(0)

            return re.sub(r"\{event\.([\w.]+)\}", _sub, value)
        if isinstance(value, list):
            return [WorkflowEngine._interpolate(item, event) for item in value]
        if isinstance(value, dict):
            return {k: WorkflowEngine._interpolate(v, event) for k, v in value.items()}
        return value

    @staticmethod
    def _fire_log(automation: Automation, event: dict, action: dict) -> None:
        """Fire a 'log' action: write a message to the application log."""
        level = (action.get("level") or "info").upper()
        message = action.get("message") or (
            f"Automation '{automation.name}' fired on {event.get('type')}"
        )
        logger.log(getattr(logging, level, logging.INFO), message)

    @staticmethod
    async def _fire_slack_webhook(automation: Automation, event: dict, action: dict) -> None:
        """Fire a 'slack_webhook' action."""
        url = action.get("webhook_url") or settings.alert_webhook_url
        if not url:
            raise ValueError("slack_webhook action requires webhook_url (or ALERT_WEBHOOK_URL)")

        text = action.get("text") or f"Automation '{automation.name}' fired"
        fields = [
            {"title": key, "value": WorkflowEngine._interpolate(val, event)}
            for key, val in (action.get("fields") or {}).items()
        ]
        payload = {
            "text": text,
            "attachments": [{"color": "warning", "fields": fields or None}],
        }
        await WebhookClient(url).send(payload)

    @staticmethod
    async def _fire_webhook(automation: Automation, event: dict, action: dict) -> None:
        """Fire a generic 'webhook' action."""
        url = action.get("url")
        if not url:
            raise ValueError("webhook action requires url")
        payload = action.get("payload") or {
            "automation": automation.name,
            "event_type": event.get("type"),
            "event": _safe_snapshot(event),
        }
        payload = WorkflowEngine._interpolate(payload, event)
        await WebhookClient(url).send(payload)

    @staticmethod
    async def _fire_retry_task(event: dict, action: dict, session: AsyncSession) -> dict:
        """Fire a 'retry_task' action using the event's task id."""
        task_id = action.get("task_id") or event.get("uuid")
        if not task_id:
            return {"error": "no task_id available"}
        result = await retry_task(task_id, session)
        return {"error": result["error"]} if "error" in result else {"task_id": task_id}

    @staticmethod
    async def _fire_execute_task(event: dict, action: dict) -> dict:
        """Fire an 'execute_task' action by name."""
        name = action.get("name") or event.get("name")
        if not name:
            return {"error": "no task name available"}
        result = await execute_task(
            name,
            args=action.get("args"),
            kwargs=action.get("kwargs"),
            queue=action.get("queue"),
            countdown=action.get("countdown"),
            eta=action.get("eta"),
            expires=action.get("expires"),
            priority=action.get("priority"),
        )
        if "error" in result:
            return {"error": result["error"]}
        return {"task_id": result.get("task_id")}

    @staticmethod
    async def _fire_revoke_task(event: dict, action: dict, session: AsyncSession) -> dict:
        """Fire a 'revoke_task' action using the event's task id."""
        task_id = action.get("task_id") or event.get("uuid")
        if not task_id:
            return {"error": "no task_id available"}
        terminate = action.get("terminate", False)
        result = await revoke_task(task_id, terminate, session)
        return {"error": result["error"]} if "error" in result else {"task_id": task_id}
