# taskowl

Modern Celery task monitoring with MCP integration. No UI, just data.

## Features

- **MCP-first**: Query tasks, workers, and queues via Model Context Protocol
- **Event sourcing**: Append-only event log for complete audit trail and timeline reconstruction
- **Real-time monitoring**: Capture Celery events as they happen
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
git clone https://github.com/KalvadTech/taskowl.git
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

## Troubleshooting

### Common Issues

#### Database Connection Errors

**Error**: `connection refused` or `role "user" does not exist`

**Solutions**:
1. Verify PostgreSQL is running: `pg_isready`
2. Check DATABASE_URL format: `postgresql+asyncpg://user:pass@host:port/dbname`
3. Verify database exists: `psql -U user -l | grep dbname`
4. Check user permissions: `psql -U postgres -c "\du"`

#### RabbitMQ Connection Errors

**Error**: `ConnectionRefusedError` or `Socket closed`

**Solutions**:
1. Verify RabbitMQ is running: `rabbitmqctl status`
2. Check CELERY_BROKER_URL format: `amqp://user:pass@host:port/vhost`
3. Verify vhost exists: `rabbitmqctl list_vhosts`
4. Check user permissions: `rabbitmqctl list_permissions`

#### Consumer Not Receiving Events

**Symptoms**: Consumer starts but no events appear in database

**Diagnostic Steps**:
1. Check consumer logs for connection success:
   ```bash
   make consume 2>&1 | grep "Connected to Celery broker"
   ```

2. Verify Celery workers are sending events:
   ```bash
   celery -A your_app events --dump
   ```

3. Check RabbitMQ queues:
   ```bash
   rabbitmqctl list_queues name messages consumers
   ```

4. Verify events are in database:
   ```sql
   SELECT COUNT(*) FROM task_events;
   SELECT COUNT(*) FROM worker_events;
   ```

#### MCP Server Not Starting

**Error**: Port already in use or connection refused

**Solutions**:
1. Check if port 8001 is in use:
   ```bash
   lsof -i :8001
   # or
   netstat -tulpn | grep 8001
   ```

2. Kill existing process:
   ```bash
   kill $(lsof -t -i :8001)
   ```

3. Verify MCP server is running:
   ```bash
   curl http://localhost:8001/mcp
   ```

#### API Server Issues

**Error**: FastAPI not starting or endpoints returning errors

**Solutions**:
1. Check if port 8000 is in use:
   ```bash
   lsof -i :8000
   ```

2. Verify API server is running:
   ```bash
   curl http://localhost:8000/health
   ```

3. Check API logs for errors:
   ```bash
   make api 2>&1 | grep ERROR
   ```

### Diagnostic Commands

**Check all services are running**:
```bash
# API server
curl -s http://localhost:8000/health

# MCP server
curl -s http://localhost:8001/mcp

# Database connection
psql $DATABASE_URL -c "SELECT 1"

# RabbitMQ connection
rabbitmqctl status
```

**Check event flow**:
```bash
# Count events in database
psql $DATABASE_URL -c "
  SELECT 
    'task_events' as table_name, 
    COUNT(*) as count 
  FROM task_events
  UNION ALL
  SELECT 
    'worker_events', 
    COUNT(*) 
  FROM worker_events
"

# Check latest events
psql $DATABASE_URL -c "
  SELECT event_type, timestamp, hostname 
  FROM task_events 
  ORDER BY timestamp DESC 
  LIMIT 5
"
```

**View logs**:
```bash
# API server logs
make api 2>&1 | tee api.log

# Consumer logs
make consume 2>&1 | tee consume.log

# MCP server logs
make mcp 2>&1 | tee mcp.log
```

### Getting Help

If you encounter issues not covered here:

1. Check existing issues: https://github.com/KalvadTech/taskowl/issues
2. Open a new issue with:
   - Error messages (full stack trace)
   - Environment details (Python version, OS, PostgreSQL version)
   - Steps to reproduce
   - Relevant logs (sanitized of sensitive data)

## License

MIT License - see [LICENSE](LICENSE) for details

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed guidelines on development setup, code style, testing, and the pull request process.

## Acknowledgments

- [Flower](https://github.com/mher/flower) - The original Celery monitor
- [Kanchi](https://github.com/getkanchi/kanchi) - Modern Celery monitoring inspiration
