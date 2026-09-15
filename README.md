<img src="logo.png" alt="taskowl" width="300"/>

# taskowl

[![Documentation](https://img.shields.io/badge/docs-github_pages-blue)](https://kalvadtech.github.io/taskowl/)

Modern Celery task monitoring with MCP integration. No UI, just data.

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

## Documentation

The full documentation lives on [GitHub Pages](https://kalvadtech.github.io/taskowl/) —
setup, configuration, a complete usage guide, and troubleshooting.

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

### Connect your Celery app

taskowl listens to Celery's **events** stream, which workers emit only if enabled:

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

> **Note**: If events are not enabled, taskowl simply sees nothing — no tasks,
> no workers.

### Connect an MCP client

The MCP server runs on `http://localhost:8001/mcp` (Streamable HTTP). For opencode:

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

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, code style,
testing, and the pull request process.

## License

MIT — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Flower](https://github.com/mher/flower) — the original Celery monitor
- [Kanchi](https://github.com/getkanchi/kanchi) — modern Celery monitoring inspiration