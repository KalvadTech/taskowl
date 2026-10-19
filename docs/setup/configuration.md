# Configuration

All configuration is via environment variables.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://localhost:5432/taskowl` | Yes |
| `CELERY_BROKER_URL` | Celery broker URL (RabbitMQ, Redis, etc.) | `amqp://guest:guest@localhost:5672//` | Yes |
| `TASKOWL_HOST` | FastAPI server host | `0.0.0.0` | No |
| `TASKOWL_PORT` | FastAPI server port | `8000` | No |
| `MCP_HOST` | MCP server host | `0.0.0.0` | No |
| `MCP_PORT` | MCP server port | `8001` | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |
| `API_KEY` | API key for authentication (optional) | None (disabled) | No |
| `ORPHAN_GRACE_SECONDS` | Wait after task started before flagging as orphan | `60` | No |
| `WORKER_OFFLINE_TIMEOUT_SECONDS` | No heartbeat for this long means worker is offline | `30` | No |
| `ALERT_WEBHOOK_URL` | Slack webhook URL to post alerts to (disabled if unset) | None | No |
| `ALERT_ON_TASK_FAILED` | Enable task-failed alerts (legacy; see Automations) | `true` | No |
| `ALERT_ON_WORKER_OFFLINE` | Enable worker-offline alerts (legacy; see Automations) | `true` | No |
| `ALERT_SLOW_TASK_SECONDS` | Alert when a succeeded task exceeds this runtime | None | No |
| `ALERT_WORKER_CHECK_SECONDS` | Interval for the periodic stale-worker check | `30` | No |
| `AUTOMATION_CHECK_SECONDS` | Interval for the periodic automation evaluation loop | `5` | No |
| `EVENT_RETENTION_DAYS` | Delete `task_events`/`worker_events` older than this many days (`0` = keep forever) | `0` | No |
| `AUTOMATION_RUN_RETENTION_DAYS` | Delete `automation_runs` older than this many days (`0` = keep forever) | `0` | No |
| `RETENTION_CHECK_SECONDS` | Interval for the consumer's periodic prune loop | `3600` | No |
| `RETENTION_BATCH_SIZE` | Rows deleted per batch when pruning | `10000` | No |

## Retention

The event log is append-only and grows without bound by default. Set
`EVENT_RETENTION_DAYS` (and optionally `AUTOMATION_RUN_RETENTION_DAYS`) to have
the consumer periodically delete rows older than the window, or run
`taskowl-prune` on demand. See [Retention](../usage/retention.md) for details.

## Brokers

TaskOwl works with any Celery/kombu broker via `CELERY_BROKER_URL`:

```bash
export CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//"   # RabbitMQ / LavinMQ
export CELERY_BROKER_URL="redis://localhost:6379/0"              # Redis
```

## Authentication

Optional API key authentication protects the REST API and MCP server. Set
`API_KEY` to enable it; all requests must then include
`Authorization: Bearer <key>`.

```bash
export API_KEY="your-secret-key-here"
curl -H "Authorization: Bearer your-secret-key-here" http://localhost:8000/api/tasks
```

When authentication is disabled, all endpoints are open. `/health`, `/`, and
`/metrics` remain open regardless.