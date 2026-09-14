"""Tests for the workflow automation evaluation engine."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.automations import create_automation
from taskowl.models import AutomationRun
from taskowl.workflow import WorkflowEngine, _resolve_field, evaluate_condition


@pytest.mark.asyncio
async def test_resolve_field_top_level():
    """Test resolving a top-level event field."""
    event = {"type": "task-failed", "name": "payments.charge", "runtime": 1.5}
    assert _resolve_field(event, "name") == "payments.charge"
    assert _resolve_field(event, "runtime") == 1.5
    assert _resolve_field(event, "missing") is None


@pytest.mark.asyncio
async def test_resolve_field_dotted():
    """Test resolving a dotted field path."""
    event = {"request": {"id": "abc", "name": "nested.task"}}
    assert _resolve_field(event, "request.id") == "abc"
    assert _resolve_field(event, "request.name") == "nested.task"
    assert _resolve_field(event, "request.missing") is None


def test_condition_eq():
    """Test eq condition."""
    event = {"name": "payments.charge"}
    assert evaluate_condition(event, {"field": "name", "op": "eq", "value": "payments.charge"})
    assert not evaluate_condition(event, {"field": "name", "op": "eq", "value": "other"})


def test_condition_neq():
    """Test neq condition."""
    event = {"name": "payments.charge"}
    assert evaluate_condition(event, {"field": "name", "op": "neq", "value": "other"})
    assert not evaluate_condition(event, {"field": "name", "op": "neq", "value": "payments.charge"})


def test_condition_gt_gte_lt_lte():
    """Test numeric comparison conditions."""
    event = {"retries": 3, "runtime": 10.5}
    assert evaluate_condition(event, {"field": "retries", "op": "gt", "value": 2})
    assert not evaluate_condition(event, {"field": "retries", "op": "gt", "value": 3})
    assert evaluate_condition(event, {"field": "retries", "op": "gte", "value": 3})
    assert evaluate_condition(event, {"field": "runtime", "op": "lt", "value": 20})
    assert evaluate_condition(event, {"field": "runtime", "op": "lte", "value": 10.5})
    assert not evaluate_condition(event, {"field": "runtime", "op": "lt", "value": 10.5})


def test_condition_contains():
    """Test contains condition."""
    event = {"name": "payments.charge", "hosts": ["a", "b"]}
    assert evaluate_condition(event, {"field": "name", "op": "contains", "value": "charge"})
    assert not evaluate_condition(event, {"field": "name", "op": "contains", "value": "refund"})
    assert evaluate_condition(event, {"field": "hosts", "op": "contains", "value": "a"})


def test_condition_matches():
    """Test matches (regex) condition."""
    event = {"exception": "ValueError: bad input"}
    assert evaluate_condition(
        event, {"field": "exception", "op": "matches", "value": r"ValueError"}
    )
    assert not evaluate_condition(
        event, {"field": "exception", "op": "matches", "value": r"TimeoutError"}
    )


def test_condition_in():
    """Test in condition."""
    event = {"queue": "high"}
    assert evaluate_condition(event, {"field": "queue", "op": "in", "value": ["high", "default"]})
    assert not evaluate_condition(event, {"field": "queue", "op": "in", "value": ["low"]})


def test_condition_exists():
    """Test exists condition."""
    event = {"exception": "boom"}
    assert evaluate_condition(event, {"field": "exception", "op": "exists"})
    assert not evaluate_condition(event, {"field": "traceback", "op": "exists"})


def test_condition_invalid():
    """Test an invalid condition returns False."""
    event = {"name": "x"}
    assert not evaluate_condition(event, {"field": "name", "op": "bogus", "value": 1})
    assert not evaluate_condition(event, {"field": None, "op": "eq", "value": 1})


@pytest.mark.asyncio
async def test_evaluate_event_matching_trigger_writes_run(db_session: AsyncSession):
    """Test a matching trigger + passing conditions writes a run."""
    await create_automation(
        {
            "name": "alert-failures",
            "trigger_type": "event",
            "event_type": "task-failed",
            "conditions": [{"field": "name", "op": "eq", "value": "payments.charge"}],
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed",
        {"type": "task-failed", "name": "payments.charge", "hostname": "w1"},
        session=db_session,
    )

    result = await db_session.execute(select(AutomationRun))
    runs = result.scalars().all()
    assert len(runs) == 1
    assert runs[0].trigger == "task-failed"
    assert runs[0].matched is True
    assert runs[0].conditions_passed is True
    assert runs[0].actions_fired == [{"type": "log"}]
    # metadata-only snapshot (no args/kwargs/results)
    assert "hostname" in runs[0].details["event"]
    assert runs[0].details["event"].get("name") == "payments.charge"


@pytest.mark.asyncio
async def test_evaluate_event_conditions_fail(db_session: AsyncSession):
    """Test a matching trigger with failing conditions records a run with no actions."""
    await create_automation(
        {
            "name": "alert-failures",
            "trigger_type": "event",
            "event_type": "task-failed",
            "conditions": [{"field": "name", "op": "eq", "value": "payments.charge"}],
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed",
        {"type": "task-failed", "name": "other.task"},
        session=db_session,
    )

    result = await db_session.execute(select(AutomationRun))
    run = result.scalars().one()
    assert run.matched is True
    assert run.conditions_passed is False
    assert run.actions_fired is None


@pytest.mark.asyncio
async def test_evaluate_event_non_matching_trigger(db_session: AsyncSession):
    """Test an event that doesn't match any automation writes nothing."""
    await create_automation(
        {
            "name": "alert-failures",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-succeeded",
        {"type": "task-succeeded", "name": "payments.charge"},
        session=db_session,
    )

    result = await db_session.execute(select(AutomationRun))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_evaluate_event_disabled_automation_skipped(db_session: AsyncSession):
    """Test disabled automations are not evaluated."""
    from taskowl.automations import toggle_automation

    created = await create_automation(
        {
            "name": "disabled",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )
    await toggle_automation(created["id"], session=db_session)

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    result = await db_session.execute(select(AutomationRun))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_evaluate_event_multiple_automations(db_session: AsyncSession):
    """Test multiple automations matching the same event each write a run."""
    await create_automation(
        {
            "name": "a",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )
    await create_automation(
        {
            "name": "b",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    result = await db_session.execute(select(AutomationRun))
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_evaluate_event_unsupported_action_logged_not_fired(db_session: AsyncSession):
    """Test unsupported action types are skipped without crashing."""
    await create_automation(
        {
            "name": "future-action",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "does_not_exist"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    result = await db_session.execute(select(AutomationRun))
    run = result.scalars().one()
    assert run.conditions_passed is True
    assert run.actions_fired == []


@pytest.mark.asyncio
async def test_evaluate_event_snapshot_omits_sensitive_fields(db_session: AsyncSession):
    """Test the run snapshot never includes args/kwargs/result/traceback."""
    await create_automation(
        {
            "name": "safe",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed",
        {
            "type": "task-failed",
            "name": "x",
            "args": ["secret"],
            "kwargs": {"key": "secret"},
            "result": {"data": "secret"},
            "traceback": "Traceback...",
            "exception": "ValueError",
        },
        session=db_session,
    )

    result = await db_session.execute(select(AutomationRun))
    snapshot = result.scalars().one().details["event"]
    assert "exception" in snapshot
    for sensitive in ("args", "kwargs", "result", "traceback"):
        assert sensitive not in snapshot


@pytest.mark.asyncio
async def test_interpolate_event_fields():
    """Test {event.field} interpolation in action params."""
    event = {"uuid": "abc-123", "name": "payments.charge", "retries": 2}
    result = WorkflowEngine._interpolate(
        {"task_id": "{event.uuid}", "label": "processing {event.name}"}, event
    )
    assert result["task_id"] == "abc-123"
    assert result["label"] == "processing payments.charge"


@pytest.mark.asyncio
async def test_fire_slack_webhook(db_session: AsyncSession):
    """Test slack_webhook action sends a payload via WebhookClient."""
    await create_automation(
        {
            "name": "slack-failures",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [
                {
                    "type": "slack_webhook",
                    "webhook_url": "http://hooks.test/x",
                    "text": "A task failed",
                    "fields": {"Task": "{event.name}", "Task ID": "{event.uuid}"},
                }
            ],
        },
        session=db_session,
    )

    with patch("taskowl.workflow.WebhookClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.send = AsyncMock()
        mock_client_cls.return_value = mock_client

        engine = WorkflowEngine()
        await engine.evaluate_event(
            "task-failed",
            {"type": "task-failed", "name": "payments.charge", "uuid": "abc"},
            session=db_session,
        )

    mock_client_cls.assert_called_once_with("http://hooks.test/x")
    mock_client.send.assert_awaited_once()
    payload = mock_client.send.call_args.args[0]
    assert payload["text"] == "A task failed"
    assert payload["attachments"][0]["fields"][0]["value"] == "payments.charge"


@pytest.mark.asyncio
async def test_fire_slack_webhook_no_url(db_session: AsyncSession):
    """Test slack_webhook without a URL records an error."""
    await create_automation(
        {
            "name": "slack-no-url",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "slack_webhook"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    result = await db_session.execute(select(AutomationRun))
    run = result.scalars().one()
    assert run.actions_fired[0]["type"] == "slack_webhook"
    assert "error" in run.actions_fired[0]


@pytest.mark.asyncio
async def test_fire_generic_webhook(db_session: AsyncSession):
    """Test generic webhook action sends the payload."""
    await create_automation(
        {
            "name": "generic-webhook",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [
                {
                    "type": "webhook",
                    "url": "http://hooks.test/y",
                    "payload": {"task": "{event.name}"},
                }
            ],
        },
        session=db_session,
    )

    with patch("taskowl.workflow.WebhookClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.send = AsyncMock()
        mock_client_cls.return_value = mock_client

        engine = WorkflowEngine()
        await engine.evaluate_event(
            "task-failed",
            {"type": "task-failed", "name": "payments.charge"},
            session=db_session,
        )

    mock_client_cls.assert_called_once_with("http://hooks.test/y")
    mock_client.send.assert_awaited_once()
    payload = mock_client.send.call_args.args[0]
    assert payload["task"] == "payments.charge"


@pytest.mark.asyncio
async def test_fire_retry_task(db_session: AsyncSession):
    """Test retry_task action dispatches to the actions module."""
    await create_automation(
        {
            "name": "retry-failures",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "retry_task"}],
        },
        session=db_session,
    )

    with patch("taskowl.workflow.retry_task") as mock_retry:
        mock_retry.return_value = {"status": "success", "new_task_id": "new-1"}

        engine = WorkflowEngine()
        await engine.evaluate_event(
            "task-failed",
            {"type": "task-failed", "name": "x", "uuid": "abc"},
            session=db_session,
        )

    mock_retry.assert_awaited_once_with("abc", db_session)
    result = await db_session.execute(select(AutomationRun))
    run = result.scalars().one()
    assert run.actions_fired == [{"type": "retry_task", "task_id": "abc"}]


@pytest.mark.asyncio
async def test_fire_execute_task(db_session: AsyncSession):
    """Test execute_task action dispatches to the actions module."""
    await create_automation(
        {
            "name": "execute-cleanup",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "execute_task", "name": "cleanup.run", "kwargs": {"x": 1}}],
        },
        session=db_session,
    )

    with patch("taskowl.workflow.execute_task") as mock_execute:
        mock_execute.return_value = {"status": "success", "task_id": "new-1"}

        engine = WorkflowEngine()
        await engine.evaluate_event(
            "task-failed", {"type": "task-failed", "name": "x", "uuid": "abc"}, session=db_session
        )

    mock_execute.assert_awaited_once_with(
        "cleanup.run",
        args=None,
        kwargs={"x": 1},
        queue=None,
        countdown=None,
        eta=None,
        expires=None,
        priority=None,
    )
    result = await db_session.execute(select(AutomationRun))
    run = result.scalars().one()
    assert run.actions_fired == [{"type": "execute_task", "task_id": "new-1"}]


@pytest.mark.asyncio
async def test_fire_revoke_task(db_session: AsyncSession):
    """Test revoke_task action dispatches to the actions module."""
    await create_automation(
        {
            "name": "revoke-failures",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "revoke_task"}],
        },
        session=db_session,
    )

    with patch("taskowl.workflow.revoke_task") as mock_revoke:
        mock_revoke.return_value = {"status": "success"}

        engine = WorkflowEngine()
        await engine.evaluate_event(
            "task-failed",
            {"type": "task-failed", "name": "x", "uuid": "abc"},
            session=db_session,
        )

    mock_revoke.assert_awaited_once_with("abc", False, db_session)
    result = await db_session.execute(select(AutomationRun))
    run = result.scalars().one()
    assert run.actions_fired == [{"type": "revoke_task", "task_id": "abc"}]


@pytest.mark.asyncio
async def test_cooldown_blocks_second_fire(db_session: AsyncSession):
    """Test cooldown_seconds prevents re-firing within the window."""
    await create_automation(
        {
            "name": "cooldown-demo",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "cooldown_seconds": 60,
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    # First event fires
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )
    # Second event within cooldown is skipped
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    result = await db_session.execute(select(AutomationRun))
    runs = result.scalars().all()
    assert len(runs) == 2
    assert runs[0].actions_fired == [{"type": "log"}]
    assert runs[1].actions_fired is None
    assert runs[1].details["skipped"] == "cooldown"


@pytest.mark.asyncio
async def test_cooldown_expires(db_session: AsyncSession):
    """Test cooldown no longer blocks once the window has passed."""
    from datetime import timedelta

    from taskowl.models import AutomationRun as Run

    await create_automation(
        {
            "name": "cooldown-expiry",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "cooldown_seconds": 10,
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    # Backdate the run so the cooldown has expired
    run = (await db_session.execute(select(Run))).scalars().one()
    run.created_at = datetime.now(UTC) - timedelta(seconds=30)
    await db_session.commit()

    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    runs = (await db_session.execute(select(Run))).scalars().all()
    assert runs[1].actions_fired == [{"type": "log"}]


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_max(db_session: AsyncSession):
    """Test max_runs_per_window blocks once the cap is reached."""
    await create_automation(
        {
            "name": "rate-limit-demo",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "max_runs_per_window": 2,
            "window_seconds": 60,
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    for _ in range(3):
        await engine.evaluate_event(
            "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
        )

    result = await db_session.execute(select(AutomationRun))
    runs = result.scalars().all()
    assert len(runs) == 3
    assert runs[0].actions_fired == [{"type": "log"}]
    assert runs[1].actions_fired == [{"type": "log"}]
    assert runs[2].actions_fired is None
    assert runs[2].details["skipped"] == "rate_limited"


@pytest.mark.asyncio
async def test_rate_limit_no_skip_within_budget(db_session: AsyncSession):
    """Test firings within the budget are not rate-limited."""
    await create_automation(
        {
            "name": "rate-budget",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "max_runs_per_window": 5,
            "window_seconds": 60,
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    for _ in range(3):
        await engine.evaluate_event(
            "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
        )

    runs = (await db_session.execute(select(AutomationRun))).scalars().all()
    assert all(run.actions_fired == [{"type": "log"}] for run in runs)


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_threshold(db_session: AsyncSession):
    """Test the circuit breaker skips actions once the failure threshold is hit."""
    await create_automation(
        {
            "name": "breaker-demo",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "circuit_breaker": {"failure_threshold": 2, "window_seconds": 60},
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    # Fire twice (reaches threshold)
    for _ in range(2):
        await engine.evaluate_event(
            "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
        )
    # Third should be circuit_open
    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    runs = (await db_session.execute(select(AutomationRun))).scalars().all()
    assert runs[0].actions_fired == [{"type": "log"}]
    assert runs[1].actions_fired == [{"type": "log"}]
    assert runs[2].actions_fired is None
    assert runs[2].details["skipped"] == "circuit_open"


@pytest.mark.asyncio
async def test_circuit_breaker_auto_closes_after_window(db_session: AsyncSession):
    """Test the circuit breaker reopens once the window has passed."""
    from datetime import timedelta

    from taskowl.models import AutomationRun as Run

    await create_automation(
        {
            "name": "breaker-closes",
            "trigger_type": "event",
            "event_type": "task-failed",
            "actions": [{"type": "log"}],
            "circuit_breaker": {"failure_threshold": 2, "window_seconds": 10},
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    for _ in range(2):
        await engine.evaluate_event(
            "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
        )

    # Backdate the fired runs so the window has passed
    runs = (await db_session.execute(select(Run))).scalars().all()
    old = datetime.now(UTC) - timedelta(seconds=30)
    for run in runs:
        run.created_at = old
    await db_session.commit()

    await engine.evaluate_event(
        "task-failed", {"type": "task-failed", "name": "x"}, session=db_session
    )

    runs = (await db_session.execute(select(Run))).scalars().all()
    assert runs[2].actions_fired == [{"type": "log"}]


@pytest.mark.asyncio
async def test_periodic_automation_fires_on_schedule(db_session: AsyncSession):
    """Test a periodic automation fires when its schedule is due."""
    await create_automation(
        {
            "name": "heartbeat",
            "trigger_type": "periodic",
            "schedule_seconds": 5,
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    # First evaluation: no prior run -> fires
    await engine.evaluate_periodic(session=db_session)
    # Second evaluation: within schedule -> not due, no run recorded
    await engine.evaluate_periodic(session=db_session)

    runs = (await db_session.execute(select(AutomationRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].trigger == "periodic"
    assert runs[0].conditions_passed is True
    assert runs[0].actions_fired == [{"type": "log"}]


@pytest.mark.asyncio
async def test_periodic_automation_fires_again_after_schedule(db_session: AsyncSession):
    """Test a periodic automation fires again once the schedule has elapsed."""
    from datetime import timedelta

    from taskowl.models import AutomationRun as Run

    await create_automation(
        {
            "name": "heartbeat-again",
            "trigger_type": "periodic",
            "schedule_seconds": 5,
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_periodic(session=db_session)

    # Backdate the run so the schedule has elapsed
    run = (await db_session.execute(select(Run))).scalars().one()
    run.created_at = datetime.now(UTC) - timedelta(seconds=10)
    await db_session.commit()

    await engine.evaluate_periodic(session=db_session)

    runs = (await db_session.execute(select(Run))).scalars().all()
    assert len(runs) == 2
    assert runs[1].actions_fired == [{"type": "log"}]


@pytest.mark.asyncio
async def test_periodic_automation_conditions_evaluated(db_session: AsyncSession):
    """Test a periodic automation with failing conditions records no actions."""
    await create_automation(
        {
            "name": "periodic-condition",
            "trigger_type": "periodic",
            "schedule_seconds": 5,
            "conditions": [{"field": "runtime", "op": "gt", "value": 10}],
            "actions": [{"type": "log"}],
        },
        session=db_session,
    )

    engine = WorkflowEngine()
    await engine.evaluate_periodic(session=db_session)

    runs = (await db_session.execute(select(AutomationRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].conditions_passed is False
    assert runs[0].actions_fired is None
