# Automations

Automations are declarative **trigger → conditions → actions** definitions that
drive workflow automation — a superset of the original env-var alerts. They are
evaluated by the consumer process, managed via the `/api/automations` endpoints,
and exposed as the `*_automation` MCP tools.

## How evaluation works

When the consumer receives an event, it loads every **enabled** event automation
whose `event_type` matches, evaluates the automation's `conditions` against the
event, and — if they all pass — fires its `actions`. Every evaluation is
recorded in the append-only `automation_runs` log (metadata only; args, kwargs,
results, and tracebacks are never stored).

Periodic automations run on a schedule instead, evaluated by the consumer's
periodic loop (`AUTOMATION_CHECK_SECONDS`, default 5).

## Anatomy of an automation

```json
{
  "name": "alert-on-failure",
  "enabled": true,
  "trigger_type": "event",
  "event_type": "task-failed",
  "conditions": [{"field": "name", "op": "eq", "value": "payments.charge"}],
  "actions": [{"type": "log"}],
  "cooldown_seconds": null,
  "max_runs_per_window": null,
  "window_seconds": null,
  "circuit_breaker": null
}
```

## Creating an automation

```bash
curl -X POST http://localhost:8000/api/automations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "alert-on-failure",
    "trigger_type": "event",
    "event_type": "task-failed",
    "conditions": [{"field": "name", "op": "eq", "value": "payments.charge"}],
    "actions": [{"type": "slack_webhook", "webhook_url": "https://hooks.slack.com/..."}]
  }'
```

## Triggers

| `trigger_type` | Required fields | Fires on |
|---|---|---|
| `event` | `event_type` | A matching Celery event (`task-failed`, `task-succeeded`, `worker-offline`, ...) |
| `periodic` | `schedule_seconds` | A schedule; conditions evaluate against an empty event context |

## Conditions

Conditions are `{field, op, value}` triples evaluated against the event. Field
paths support dots (e.g. `request.id`). All conditions must pass.

| Op | Behavior |
|---|---|
| `eq` | Field equals value |
| `neq` | Field does not equal value |
| `gt` / `gte` | Field greater than / greater-or-equal (numeric) |
| `lt` / `lte` | Field less than / less-or-equal (numeric) |
| `contains` | String contains value, or list/dict contains value |
| `matches` | Field (stringified) matches a regex |
| `in` | Field is in a list |
| `exists` | Field is present (non-null) |

Example — only alert for retried failures of one task on the high queue:

```json
{
  "conditions": [
    {"field": "name", "op": "eq", "value": "payments.charge"},
    {"field": "retries", "op": "gte", "value": 1},
    {"field": "queue", "op": "in", "value": ["high", "critical"]}
  ]
}
```

## Actions

| Type | Parameters |
|---|---|
| `log` | `level`, `message` |
| `slack_webhook` | `webhook_url` (or `ALERT_WEBHOOK_URL`), `text`, `fields` (dict of `{label: value}`) |
| `webhook` | `url`, `payload` (JSON) |
| `retry_task` | `task_id` (defaults to event `uuid`) |
| `execute_task` | `name`, `args`, `kwargs`, `queue`, `countdown`, `eta`, `expires`, `priority` |
| `revoke_task` | `task_id` (defaults to event `uuid`), `terminate` |
| `check_workers_offline` | `webhook_url` — scan for stale workers and alert |

Action params support **`{event.field}` interpolation** — the value is resolved
from the triggering event at fire time:

```json
{
  "type": "webhook",
  "url": "https://example.com/hooks",
  "payload": {"task_id": "{event.uuid}", "task_name": "{event.name}"}
}
```

## Safety knobs

Prevent alert/action storms:

- **`cooldown_seconds`** — after firing, wait at least this long before firing again.
- **`max_runs_per_window` + `window_seconds`** — fire at most `max_runs_per_window`
  times per `window_seconds`.
- **`circuit_breaker`** — `{"failure_threshold": N, "window_seconds": W}`; skip
  actions (`circuit_open`) once the automation has fired N times within W
  seconds, and auto-close once the window rolls past.

Skipped evaluations are still recorded in `automation_runs` with a
`details.skipped` reason: `"cooldown"`, `"rate_limited"`, or `"circuit_open"`.

## Observability

- **Run history**: `GET /api/automations/{id}/runs` / `get_automation_runs`.
- **Status + circuit state**: `GET /api/automations/{id}/status` /
  `get_automation_status` returns the automation, its latest run, and whether
  the circuit is `open` or `closed`.
- **Prometheus**: `taskowl_automation_fired_total` and
  `taskowl_automation_skipped_total` counters.

## Worked example: retry with circuit breaker

1. Retry `payments.charge` on failure, but never more than twice per hour and
   pause entirely if it fails 3 times within 5 minutes:

```json
{
  "name": "retry-payments",
  "trigger_type": "event",
  "event_type": "task-failed",
  "conditions": [{"field": "name", "op": "eq", "value": "payments.charge"}],
  "actions": [{"type": "execute_task", "name": "payments.charge", "countdown": 30}],
  "max_runs_per_window": 2,
  "window_seconds": 3600,
  "circuit_breaker": {"failure_threshold": 3, "window_seconds": 300}
}
```

2. Tell the team when it finally trips the breaker:

```json
{
  "name": "payments-breaker-alert",
  "trigger_type": "event",
  "event_type": "task-failed",
  "conditions": [{"field": "name", "op": "eq", "value": "payments.charge"}],
  "actions": [{
    "type": "slack_webhook",
    "webhook_url": "https://hooks.slack.com/...",
    "text": "payments.charge is failing repeatedly",
    "fields": {"Task": "{event.name}", "Error": "{event.exception}"}
  }],
  "cooldown_seconds": 300
}
```

## Legacy env-var alerts

The `ALERT_*` env vars are **deprecated**. On consumer startup they seed the
equivalent built-in automations (`alert-task-failed`, `alert-slow-task`,
`alert-worker-offline`, `alert-worker-offline-sweep`), which are then managed
like any other automation. Prefer defining automations directly.