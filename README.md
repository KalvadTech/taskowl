# taskowl

Modern Celery task monitoring with MCP integration. No UI, just data.

## Features

- **MCP-first**: Query tasks, workers, and queues via Model Context Protocol
- **Event sourcing**: Append-only event log for complete audit trail and timeline reconstruction
- **Real-time monitoring**: Capture Celery events as they happen
- **Shaper integration**: Use [Shaper](https://github.com/taleshape-com/shaper) for SQL-based dashboards
- **PostgreSQL backend**: Production-ready, no SQLite fallback complexity
- **Modern stack**: Python 3.14, FastAPI, async everything

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL 14+
- RabbitMQ (or other Celery broker)
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/yourusername/taskowl.git
cd taskowl
make install

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/taskowl"
export CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//"

# Run database migrations
make migrate

# Start the API server
make api

# In another terminal, start the event consumer
make consume

# In another terminal, start the MCP server
make mcp
```

### MCP Usage

The MCP server runs on port 8001 by default. Configure your MCP client:

```json
{
  "mcpServers": {
    "taskowl": {
      "type": "remote",
      "url": "http://localhost:8001/mcp",
      "enabled": true,
      "oauth": false
    }
  }
}
```

Then ask your LLM:
- "Show me the last 10 failed tasks"
- "What's the average task runtime in the last hour?"
- "Which workers are currently online?"
- "Show me the timeline for task abc-123-def"

### REST API

The API server (started with `make api`) exposes REST endpoints that the MCP server uses internally. You can also call these endpoints directly:

**Base URL:** `http://localhost:8000`

#### GET /api/tasks

List tasks with optional filters.

**Query Parameters:**
- `state` (optional): Filter by state (received, started, succeeded, failed, retried, revoked)
- `name` (optional): Filter by task name
- `worker` (optional): Filter by worker hostname
- `since` (optional): Only tasks created after this datetime (ISO 8601)
- `limit` (optional): Max number of tasks to return (default: 100)

**Example:**
```bash
curl "http://localhost:8000/api/tasks?state=failed&limit=10"
```

#### GET /api/tasks/{task_id}

Get detailed information about a specific task.

**Example:**
```bash
curl "http://localhost:8000/api/tasks/abc-123-def"
```

#### GET /api/tasks/{task_id}/timeline

Get a chronological timeline of all events for a specific task.

**Example:**
```bash
curl "http://localhost:8000/api/tasks/abc-123-def/timeline"
```

#### GET /api/tasks/summary

Get aggregate task statistics.

**Query Parameters:**
- `hours` (optional): Time window in hours (default: 1)

**Example:**
```bash
curl "http://localhost:8000/api/tasks/summary?hours=24"
```

#### GET /api/workers

Get status of all Celery workers.

**Example:**
```bash
curl "http://localhost:8000/api/workers"
```

### Shaper Integration

Connect Shaper to the same PostgreSQL database and write SQL:

```sql
-- Tasks per hour (reconstructed from latest events)
SELECT
  date_trunc('hour', timestamp)::XAXIS,
  event_type::CATEGORY,
  count(DISTINCT task_id)::BARCHART_STACKED
FROM task_events
WHERE timestamp > now() - interval '24 hours'
GROUP BY ALL
ORDER BY ALL;

-- Task timeline (all events for a specific task)
SELECT
  timestamp::XAXIS,
  event_type::LABEL,
  hostname::CATEGORY
FROM task_events
WHERE task_id = 'abc-123-def'
ORDER BY timestamp;

-- Worker activity over time
SELECT
  date_trunc('minute', timestamp)::XAXIS,
  hostname::CATEGORY,
  avg(active)::LINECHART
FROM worker_events
WHERE event_type = 'heartbeat'
  AND timestamp > now() - interval '1 hour'
GROUP BY ALL
ORDER BY ALL;
```

See [Shaper docs](https://github.com/taleshape-com/shaper) for more.

## Configuration

All configuration is via environment variables:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://localhost:5432/taskowl` | Yes |
| `CELERY_BROKER_URL` | RabbitMQ connection string | `amqp://guest:guest@localhost:5672//` | Yes |
| `TASKOWL_HOST` | FastAPI server host | `0.0.0.0` | No |
| `TASKOWL_PORT` | FastAPI server port | `8000` | No |
| `MCP_HOST` | MCP server host | `0.0.0.0` | No |
| `MCP_PORT` | MCP server port | `8001` | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |

## MCP Tools

The MCP server (started with `make mcp`) provides tools that internally call the REST API endpoints. These tools are available to LLMs via the Model Context Protocol.

### list_tasks

List tasks with optional filters. State is reconstructed from the latest event for each task.

**Parameters:**
- `state` (optional): Filter by state (received, started, succeeded, failed, retried, revoked)
- `name` (optional): Filter by task name
- `worker` (optional): Filter by worker hostname
- `since` (optional): Only tasks created after this datetime (ISO 8601)
- `limit` (optional): Max number of tasks to return (default: 100)

**Example:**
```
Show me failed tasks from the last hour
```

**Calls:** `GET /api/tasks`

### get_task

Get detailed information about a specific task, including all events in chronological order.

**Parameters:**
- `task_id`: UUID of the task

**Example:**
```
Show me details for task abc-123-def
```

**Calls:** `GET /api/tasks/{task_id}`

### get_task_timeline

Get a chronological timeline of all events for a specific task. Perfect for debugging and understanding task execution flow.

**Parameters:**
- `task_id`: UUID of the task

**Example:**
```
Show me the timeline for task abc-123-def
```

**Calls:** `GET /api/tasks/{task_id}/timeline`

### get_task_summary

Get aggregate task statistics reconstructed from the latest events.

**Parameters:**
- `hours` (optional): Time window in hours (default: 1)

**Example:**
```
What's the task success rate in the last 30 minutes?
```

**Calls:** `GET /api/tasks/summary`

### get_worker_status

Get status of all Celery workers reconstructed from the latest events.

**Example:**
```
Which workers are online?
```

**Calls:** `GET /api/workers`

## Development

### Setup

```bash
# Install dependencies
make install

# Run tests
make test

# Lint
make lint
make lint-fix

# Type check
make typecheck

# Run all checks
make check
```

### Running Locally

```bash
# Start PostgreSQL and RabbitMQ (e.g., with Docker Compose or locally)

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/taskowl"
export CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//"

# Run migrations
make migrate

# Start the API server
make api

# In another terminal, start the event consumer
make consume
```

### Testing with Sample Data

Generate realistic test data to see taskowl in action:

```bash
# Start the consumer first
make consume

# In another terminal, generate test data
python scripts/generate_test_data.py

# Or with custom options
python scripts/generate_test_data.py --tasks 100 --hours 24 --slow-tasks 20
```

The script generates:
- Task events (received, started, succeeded/failed/retried)
- Worker events (online, heartbeat, offline)
- Realistic task names and worker hostnames
- Configurable success/failure/retry ratios

Then query via MCP to see the data:
- "Show me failed tasks"
- "Show task timeline for [task-id]"
- "Which workers are online?"

### Project Structure

```
taskowl/
├── src/taskowl/
│   ├── main.py              # FastAPI app with REST API endpoints
│   ├── config.py            # Environment variables
│   ├── database.py          # Database connection
│   ├── models.py            # SQLAlchemy models (TaskEvent, WorkerEvent)
│   ├── queries.py           # Reusable query functions
│   ├── consumer/            # Celery event consumer
│   │   ├── cli.py           # Consumer CLI entry point
│   │   ├── handlers.py      # Event handler functions
│   │   └── receiver.py      # Celery event receiver
│   └── mcp/
│       ├── server.py        # MCP server
│       ├── cli.py           # MCP CLI entry point
│       └── tools.py         # MCP tools (call REST API)
├── scripts/
│   └── generate_test_data.py  # Test data generator
├── tests/
├── alembic/
├── pyproject.toml
└── README.md
```

## Database Schema

taskowl uses an **event sourcing** architecture. Instead of storing current state, we store every event that happens. This gives us:
- Complete audit trail
- Ability to reconstruct state at any point in time
- Task timelines showing the full execution flow
- Better debugging and analysis capabilities

### task_events

Append-only log of all task events.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-incrementing ID (primary key) |
| event_type | VARCHAR(50) | Event type (sent, received, started, succeeded, failed, revoked, retried, rejected) |
| task_id | UUID | Celery task ID |
| timestamp | TIMESTAMP | Event timestamp |
| hostname | VARCHAR(255) | Worker hostname (if applicable) |
| name | VARCHAR(255) | Task name (from received event) |
| args | JSON | Task arguments (from received event) |
| kwargs | JSON | Task keyword arguments (from received event) |
| result | JSON | Task result (from succeeded event) |
| exception | TEXT | Exception type (from failed event) |
| traceback | TEXT | Error traceback (from failed event) |
| runtime | FLOAT | Task runtime in seconds (from succeeded event) |
| retries | INTEGER | Number of retries (from received/retried event) |
| eta | TIMESTAMP | ETA for task (from received event) |
| expires | TIMESTAMP | Expiration time (from received event) |
| queue | VARCHAR(255) | Queue name (from received event) |
| root_id | UUID | Root task ID (from received event) |
| parent_id | UUID | Parent task ID (from received event) |
| pid | INTEGER | Process ID (from started event) |
| signum | INTEGER | Signal number (from revoked event) |
| terminated | BOOLEAN | Whether task was terminated (from revoked event) |
| expired | BOOLEAN | Whether task expired (from revoked event) |
| requeue | BOOLEAN | Whether task was requeued (from rejected event) |
| created_at | TIMESTAMP | When this event record was created |

### worker_events

Append-only log of all worker events.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-incrementing ID (primary key) |
| event_type | VARCHAR(50) | Event type (online, heartbeat, offline) |
| hostname | VARCHAR(255) | Worker hostname |
| timestamp | TIMESTAMP | Event timestamp |
| active | INTEGER | Number of active tasks (from heartbeat) |
| processed | BIGINT | Total tasks processed (from heartbeat) |
| freq | FLOAT | Heartbeat frequency (from heartbeat) |
| sw_ident | VARCHAR(255) | Software identifier (from heartbeat/online) |
| sw_ver | VARCHAR(255) | Software version (from heartbeat/online) |
| sw_sys | VARCHAR(255) | Operating system (from heartbeat/online) |
| created_at | TIMESTAMP | When this event record was created |

## License

MIT License - see [LICENSE](LICENSE) for details

## Contributing

Contributions welcome! Please open an issue or PR.

## Acknowledgments

- [Flower](https://github.com/mher/flower) - The original Celery monitor
- [Kanchi](https://github.com/getkanchi/kanchi) - Modern Celery monitoring inspiration
- [Shaper](https://github.com/taleshape-com/shaper) - SQL-first dashboards
