<img src="logo.png" alt="TaskOwl" width="300"/>

# TaskOwl

[![CI](https://github.com/KalvadTech/taskowl/actions/workflows/ci.yml/badge.svg)](https://github.com/KalvadTech/taskowl/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-github_pages-blue)](https://kalvadtech.github.io/taskowl/)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://github.com/KalvadTech/taskowl/pkgs/container/taskowl)

**Celery monitoring for humans and AI agents. No UI, just data.**

Celery gives you workers and tasks. TaskOwl gives you observability, history,
control, and an AI interface for the whole cluster.

Celery's event stream contains a huge amount of useful operational information,
but once an event has passed, it is gone. TaskOwl turns that stream into a
persistent operational history and exposes it through REST and MCP.

## Why TaskOwl?

```
Celery workers
      │
      │ events
      ▼
   Broker
      │
      ▼
 TaskOwl Consumer
      │
      ▼
 PostgreSQL
      │
      ├── REST API
      │
      ├── Prometheus
      │
      └── MCP
            │
            ▼
       AI assistant
```

TaskOwl subscribes to Celery's events, appends every one to PostgreSQL as an
append-only log, and reconstructs current task, worker, and queue state from it.
The REST API and the MCP server are thin interfaces over that same data, so
scripts, automations, and AI agents all get the same capabilities.

It is **not** another Flower. No dashboard to click through; instead, durable
history and a control plane you can drive programmatically. See
[Why TaskOwl?](https://kalvadtech.github.io/taskowl/why-taskowl/) for the
full story.

## Ask your infrastructure

Point any MCP client at TaskOwl and operate the cluster in natural language
(**28 MCP tools** under the hood):

```text
You:     Show me failed payment tasks in the last hour.

TaskOwl: 17 failed
         12 payments.charge
          3 payments.refund
          2 payments.capture

         Most common error:
         ConnectionError: upstream timeout
```

```text
You:     Retry the failed payments.charge tasks.

TaskOwl: Retried 12 tasks.
         Retry chain preserved.
```

```text
You:     Which workers are online?

TaskOwl: 3 workers online: celery@worker1, celery@worker2, celery@worker3.
```

```text
You:     Restart the pool on celery@worker1.

TaskOwl: Pool restarted on celery@worker1.
```

## Features

- **MCP-first**: Query and manage tasks, workers, and queues via the Model Context Protocol
- **Event sourcing**: Append-only event log for a complete audit trail and state reconstruction
- **Real-time monitoring**: Capture Celery events as they happen
- **Task actions**: Revoke, retry, recover orphaned tasks, and execute tasks by name
- **Worker management**: List, inspect, scale, restart, and shut down workers
- **Queue monitoring**: Per-queue message and consumer counts for any kombu broker
- **Workflow automations**: Declarative trigger → conditions → actions engine with
  webhooks, retry orchestration, cooldowns, rate limits, and circuit breakers
- **Prometheus metrics**: Scrape task, worker, and automation telemetry via `/metrics`
- **PostgreSQL backend**: Production-ready, async throughout
- **Broker-agnostic**: RabbitMQ, LavinMQ, Redis, or any Celery/kombu broker

## Quick Start

### Try it with Docker (5 minutes)

The fastest way to see TaskOwl working is the bundled demo: PostgreSQL,
RabbitMQ, TaskOwl, a demo Celery worker, and a task producer.

```bash
git clone https://github.com/KalvadTech/taskowl.git
cd taskowl
docker compose --profile demo up --build
```

TaskOwl is now running:

| Service | URL |
|---|---|
| REST API | http://localhost:8000 |
| REST API docs | http://localhost:8000/docs |
| MCP server | http://localhost:8001/mcp |
| RabbitMQ management | http://localhost:15672 (guest / guest) |

The demo producer continuously creates tasks (including some that fail), so you
can start asking questions immediately. For just the infrastructure without the
demo workload, run `docker compose up --build`.

### Connect an MCP client

The MCP server runs on `http://localhost:8001/mcp` (Streamable HTTP). For
[opencode](https://opencode.ai):

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

Then ask: *"Show me the current tasks."*

### Run from source

Requires Python 3.14+, PostgreSQL 14+, a Celery broker, and
[uv](https://github.com/astral-sh/uv).

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

### Connect your Celery app

TaskOwl listens to Celery's **events** stream, which workers emit only if enabled:

```python
# celery_app.py
from celery import Celery

app = Celery("myapp", broker="amqp://guest:guest@localhost:5672//")

app.conf.worker_send_task_events = True
app.conf.task_send_sent_event = True
app.conf.worker_heartbeat_interval = 2
```

Or start your worker with `-E`:

```bash
celery -A myapp worker -E --loglevel=info
```

> **Note**: If events are not enabled, TaskOwl simply sees nothing, no tasks,
> no workers.

## Documentation

The full documentation lives on [GitHub Pages](https://kalvadtech.github.io/taskowl/):
setup, configuration, a complete usage guide, security, and troubleshooting.

## Security

TaskOwl can **operate** your cluster, not just observe it: execute tasks, revoke
tasks, restart pools, and shut down workers. Authentication is optional and off
by default; set `API_KEY` before exposing it to any network. See the
[Security](https://kalvadtech.github.io/taskowl/security/) page.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, code style,
testing, and the pull request process.

## License

MIT - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Flower](https://github.com/mher/flower) - the original Celery monitor
- [Kanchi](https://github.com/getkanchi/kanchi) - modern Celery monitoring inspiration
