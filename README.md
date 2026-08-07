# taskowl

Modern Celery task monitoring with MCP integration. No UI, just data.

## Features

- **MCP-first**: Query tasks, workers, and queues via Model Context Protocol
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

# Start the server
make api
```

### MCP Usage

The MCP server is available at `/mcp` endpoint. Configure your MCP client:

```json
{
  "mcpServers": {
    "taskowl": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Then ask your LLM:
- "Show me the last 10 failed tasks"
- "What's the average task runtime in the last hour?"
- "Which workers are currently online?"

### Shaper Integration

Connect Shaper to the same PostgreSQL database and write SQL:

```sql
-- Tasks per hour
SELECT
  date_trunc('hour', created_at)::XAXIS,
  state::CATEGORY,
  count(*)::BARCHART_STACKED
FROM tasks
WHERE created_at > now() - interval '24 hours'
GROUP BY ALL
ORDER BY ALL;

-- Slow tasks
SELECT
  name::LABEL,
  avg(runtime)::BARCHART
FROM tasks
WHERE state = 'SUCCESS'
  AND finished_at > now() - interval '1 hour'
GROUP BY name
ORDER BY avg(runtime) DESC
LIMIT 10;
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
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |

## MCP Tools

### list_tasks

List tasks with optional filters.

**Parameters:**
- `state` (optional): Filter by state (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED)
- `name` (optional): Filter by task name
- `worker` (optional): Filter by worker hostname
- `since` (optional): Only tasks created after this datetime
- `limit` (optional): Max number of tasks to return (default: 100)

**Example:**
```
Show me failed tasks from the last hour
```

### get_task

Get detailed information about a specific task.

**Parameters:**
- `task_id`: UUID of the task

**Example:**
```
Show me details for task abc-123-def
```

### get_task_summary

Get aggregate task statistics.

**Parameters:**
- `since` (optional): Time window (default: 1 hour)

**Example:**
```
What's the task success rate in the last 30 minutes?
```

### get_worker_status

Get status of all Celery workers.

**Example:**
```
Which workers are online?
```

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

# Start the server
make api
```

### Project Structure

```
taskowl/
├── src/taskowl/
│   ├── main.py          # FastAPI app
│   ├── config.py        # Environment variables
│   ├── database.py      # Database connection
│   ├── models.py        # SQLAlchemy models
│   ├── consumer.py      # Celery event consumer
│   └── mcp/
│       ├── server.py    # MCP server
│       └── tools.py     # MCP tools
├── tests/
├── alembic/
├── pyproject.toml
└── README.md
```

## Database Schema

### tasks

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Task ID (primary key) |
| name | VARCHAR(255) | Task name |
| state | VARCHAR(50) | Task state (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED) |
| args | JSON | Task arguments |
| kwargs | JSON | Task keyword arguments |
| result | JSON | Task result |
| traceback | TEXT | Error traceback (if failed) |
| worker | VARCHAR(255) | Worker hostname |
| queue | VARCHAR(255) | Queue name |
| started_at | TIMESTAMP | When task started |
| finished_at | TIMESTAMP | When task finished |
| runtime | FLOAT | Task runtime in seconds |
| created_at | TIMESTAMP | When task was created |
| updated_at | TIMESTAMP | When task was last updated |

### workers

| Column | Type | Description |
|--------|------|-------------|
| hostname | VARCHAR(255) | Worker hostname (primary key) |
| status | VARCHAR(50) | Worker status (online, offline) |
| pool_size | INT | Worker pool size |
| active_count | INT | Number of active tasks |
| processed_count | BIGINT | Total tasks processed |
| loadavg | JSON | System load average |
| last_heartbeat | TIMESTAMP | Last heartbeat timestamp |
| created_at | TIMESTAMP | When worker was first seen |
| updated_at | TIMESTAMP | When worker was last updated |

## License

MIT License - see [LICENSE](LICENSE) for details

## Contributing

Contributions welcome! Please open an issue or PR.

## Acknowledgments

- [Flower](https://github.com/mher/flower) - The original Celery monitor
- [Kanchi](https://github.com/getkanchi/kanchi) - Modern Celery monitoring inspiration
- [Shaper](https://github.com/taleshape-com/shaper) - SQL-first dashboards
