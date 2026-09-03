<img src="logo.png" alt="taskowl" width="300"/>

# taskowl

Modern Celery task monitoring with MCP integration. No UI, just data.

## Features

- **MCP-first**: Query and manage tasks, workers, and queues via the Model Context Protocol
- **Event sourcing**: Append-only event log for a complete audit trail and state reconstruction
- **Real-time monitoring**: Capture Celery events as they happen
- **Task actions**: Revoke, retry, and recover orphaned tasks
- **Worker management**: List, inspect, scale, and shut down workers
- **Alerts**: Slack-compatible webhook notifications on failures, slow tasks, and offline workers
- **Prometheus metrics**: Scrape task and worker telemetry via `/metrics`
- **PostgreSQL backend**: Production-ready, async throughout
- **Broker-agnostic**: RabbitMQ, LavinMQ, Redis, or any Celery/kombu broker

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL 14+
- A Celery broker (RabbitMQ, LavinMQ, Redis, ...)
- [uv](https://github.com/astral-sh/uv)

### Installation

```bash
git clone https://github.com/KalvadTech/taskowl.git
cd taskowl
make install

export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/taskowl"
export CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//"

make migrate
```

Run the three processes (separate terminals):

```bash
make api       # REST API on :8000
make consume   # Celery event consumer
make mcp       # MCP server on :8001
```

## Configuring your Celery app

taskowl listens to Celery's **events** stream, which workers emit only if
enabled. Add this to your Celery application so taskowl can see your tasks and
workers:

```python
# celery_app.py
from celery import Celery

app = Celery("myapp", broker="amqp://guest:guest@localhost:5672//")

# Workers emit task/worker events (sent, received, started, succeeded, failed, ...)
app.conf.worker_send_task_events = True

# Emit a 'task-sent' event when a task is published
app.conf.task_send_sent_event = True

# How often workers send a heartbeat (default: 2s). Higher values
# increase the worker-offline detection delay.
app.conf.worker_heartbeat_interval = 2
```

Alternatively, start your worker with the `-E` flag, which is equivalent to
`worker_send_task_events = True`:

```bash
celery -A myapp worker -E --loglevel=info
```

> **Note**: If events are not enabled, taskowl simply sees nothing — no tasks,
> no workers. Enabling events is the one integration required.

## Connecting MCP clients

The MCP server runs on `http://localhost:8001/mcp` (Streamable HTTP).

### opencode

Add a remote MCP server to your `opencode.json`:

```json
{
  "mcp": {
    "taskowl": {
      "type": "remote",
      "url": "http://localhost:8001/mcp",
      "enabled": true,
      "oauth": false
    }
  }
}
```

### Other MCP clients

Point your MCP client at the Streamable HTTP endpoint `http://localhost:8001/mcp`.
If authentication is enabled (see below), send the taskowl API key as
`Authorization: Bearer <key>` with each request.

## Available tools

| Category | Tools |
|---|---|
| **Tasks** | `list_tasks`, `get_task`, `get_task_timeline`, `get_task_chain`, `get_task_summary`, `list_task_types`, `list_orphaned_tasks` |
| **Task actions** | `revoke_task`, `retry_task`, `execute_task` |
| **Workers** | `get_worker_status`, `list_workers`, `get_worker_stats`, `shutdown_worker`, `scale_worker_pool`, `get_active_tasks` |
| **Queues** | `list_queues` |

**Total: 17 tools**

`list_tasks` supports exact filters (`state`, `name`, `worker`, `since`), a partial
case-insensitive `search` on the task name, `offset` for pagination, and `sort_by`
(`timestamp` [default, newest-first], `name`, `state`, `worker`).

## Examples

Questions you can ask your AI assistant when the MCP server is connected:

| Question | Tools used |
|---|---|
| "Show me failed tasks from the last hour" | `list_tasks` |
| "Which task types are running?" | `list_task_types` |
| "Which tasks are orphaned?" | `list_orphaned_tasks` |
| "Show me the timeline for task abc" | `get_task_timeline` |
| "What's the retry chain for task abc?" | `get_task_chain` |
| "What's the task success rate in the last 30 minutes?" | `get_task_summary` |
| "Which workers are online?" | `get_worker_status`, `list_workers` |
| "How many messages are in each queue?" | `list_queues` |
| "Shutdown worker celery@worker1" | `shutdown_worker` |
| "Retry task abc" | `retry_task` |
| "Run myapp.tasks.process now" | `execute_task` |

## Architecture

```
Celery workers ──events──▶ Broker ──▶ taskowl consumer ──▶ PostgreSQL
                                                              │
                         REST API ◀───────────────────────────┘
                              ▲
                              │ HTTP
                         MCP server ──▶ LLM / MCP client
```

- **Consumer** (separate process) captures Celery events and appends them to
  PostgreSQL (`task_events`, `worker_events`).
- **REST API** serves queries and actions over the event-sourcing tables.
- **MCP server** is a thin wrapper that calls the REST API for LLM access.

## Configuration

All configuration is via environment variables:

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
| `ALERT_ON_TASK_FAILED` | Enable task-failed alerts | `true` | No |
| `ALERT_ON_WORKER_OFFLINE` | Enable worker-offline alerts | `true` | No |
| `ALERT_SLOW_TASK_SECONDS` | Alert when a succeeded task exceeds this runtime | None | No |
| `ALERT_WORKER_CHECK_SECONDS` | Interval for the periodic stale-worker check | `30` | No |

### Brokers

taskowl works with any Celery/kombu broker via `CELERY_BROKER_URL`:

```bash
export CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//"   # RabbitMQ / LavinMQ
export CELERY_BROKER_URL="redis://localhost:6379/0"              # Redis
```

### Alerts / Webhooks

Set `ALERT_WEBHOOK_URL` to a Slack incoming webhook to receive notifications on
task failures, offline workers, and slow tasks. Alerting is **off by default**.

```bash
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
```

Conditions:

- `ALERT_ON_TASK_FAILED=true` (default) — notify when a task fails
- `ALERT_ON_WORKER_OFFLINE=true` (default) — notify when a worker goes offline
  (via an `worker-offline` event or a stale heartbeat detected every
  `ALERT_WORKER_CHECK_SECONDS`)
- `ALERT_SLOW_TASK_SECONDS=30` — notify when a succeeded task exceeds 30s

Payloads are Slack-formatted and contain task metadata only (name, task ID,
worker, error, runtime) — args, kwargs, and results are never sent.

### Prometheus Metrics

Scrape task and worker telemetry from the API server:

```bash
curl http://localhost:8000/metrics
```

```yaml
scrape_configs:
  - job_name: taskowl
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets: ["localhost:8000"]
```

| Metric | Type | Labels |
|--------|------|--------|
| `taskowl_task_events_total` | Counter | `event_type`, `task_name`, `worker` |
| `taskowl_task_execution_duration_seconds` | Histogram | `task_name` |
| `taskowl_worker_status` | Gauge (1 = online, 0 = offline) | `worker` |
| `taskowl_worker_active_tasks` | Gauge | `worker` |
| `taskowl_worker_processed_total` | Counter | `worker` |

> **Security**: `/metrics` is intentionally unauthenticated so Prometheus can
> scrape it without the taskowl API key. Only expose it to trusted networks or
> behind a reverse proxy.

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

## REST API

The API server (port 8000) exposes a REST API for tasks, workers, orphans,
retries, and metrics. Interactive docs are available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Raw OpenAPI schema: `http://localhost:8000/openapi.json`

| Area | Endpoints |
|------|-----------|
| **Tasks** | `GET /api/tasks`, `GET /api/tasks/{id}`, `GET /api/tasks/{id}/timeline`, `GET /api/tasks/{id}/chain`, `GET /api/tasks/summary`, `GET /api/tasks/types`, `GET /api/tasks/orphaned` |
| **Task actions** | `POST /api/tasks/{id}/revoke`, `POST /api/tasks/{id}/retry`, `POST /api/tasks/execute` |
| **Workers** | `GET /api/workers`, `GET /api/workers/list`, `GET /api/workers/{name}/stats`, `GET /api/workers/active-tasks` |
| **Worker actions** | `POST /api/workers/{name}/shutdown`, `POST /api/workers/{name}/scale` |
| **Queues** | `GET /api/queues` |
| **Ops** | `GET /health`, `GET /metrics` |

The `/openapi.json` schema is the authoritative reference — this README lists
only endpoint groups.

## Troubleshooting

### Worker not appearing / no events in the database

1. Verify workers emit events — start with `-E` or set `worker_send_task_events`.
2. Check the consumer connected:
   ```bash
   make consume 2>&1 | grep "Connected to Celery broker"
   ```
3. Verify events reach the broker:
   ```bash
   celery -A your_app events --dump
   ```
4. Check event counts in the database:
   ```sql
   SELECT COUNT(*) FROM task_events;
   SELECT COUNT(*) FROM worker_events;
   ```

### Database connection errors

- `pg_isready` to confirm PostgreSQL is up.
- Check `DATABASE_URL` format: `postgresql+asyncpg://user:pass@host:port/dbname`.
- Verify the role has access to the database.

### Broker connection errors

- `rabbitmqctl status` (or your broker's health check) to confirm it's running.
- Check `CELERY_BROKER_URL` format and credentials.

### Port already in use

- API: `lsof -i :8000` / MCP: `lsof -i :8001`
- Kill the offending process: `kill $(lsof -t -i :8001)`

### Getting help

Open an issue with the error message, environment details, steps to reproduce,
and relevant (sanitized) logs:
https://github.com/KalvadTech/taskowl/issues

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, code style,
testing, and the pull request process.

## License

MIT — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Flower](https://github.com/mher/flower) — the original Celery monitor
- [Kanchi](https://github.com/getkanchi/kanchi) — modern Celery monitoring inspiration
