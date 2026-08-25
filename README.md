<img src="logo.png" alt="taskowl" width="300"/>

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
- A Celery broker: RabbitMQ (or LavinMQ), Redis, etc.
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

#### GET /api/tasks/orphaned

List tasks currently considered orphaned (stuck in `STARTED` state whose worker went offline).

**Query Parameters:**
- `limit` (optional): Max number of tasks to return (default: 100)

**Example:**
```bash
curl "http://localhost:8000/api/tasks/orphaned"
```

**Response:**
```json
[
  {
    "id": "abc-123-def",
    "name": "myapp.tasks.process_data",
    "state": "orphaned",
    "worker": "celery@worker1",
    "queue": "default",
    "started_at": "2026-08-24T14:03:00Z"
  }
]
```

**Note:** A task is orphaned when it is in `STARTED` state, its `started` timestamp is older than `ORPHAN_GRACE_SECONDS`, and its worker has been offline for longer than `WORKER_OFFLINE_TIMEOUT_SECONDS`.

#### GET /api/workers

Get status of all Celery workers. The `status` field is derived from worker events: `online` if a heartbeat was received within `WORKER_OFFLINE_TIMEOUT_SECONDS`, `offline` if the worker sent an offline event or its last heartbeat is stale, and `unknown` if no worker events exist. `last_event` contains the raw last event type.

**Example:**
```bash
curl "http://localhost:8000/api/workers"
```

#### GET /api/workers/list

List all active Celery workers.

**Example:**
```bash
curl "http://localhost:8000/api/workers/list"
```

**Response:**
```json
{
  "workers": [
    {
      "name": "celery@worker1",
      "status": "online"
    }
  ]
}
```

#### GET /api/workers/{worker_name}/stats

Get detailed statistics for a specific worker.

**Example:**
```bash
curl "http://localhost:8000/api/workers/celery@worker1/stats"
```

**Response:**
```json
{
  "stats": {
    "pool": {
      "max-concurrency": 4,
      "processes": [4321, 4322, 4323, 4324]
    },
    "uptime": 3600,
    "pid": 1234
  }
}
```

#### POST /api/workers/{worker_name}/shutdown

Gracefully shutdown a worker.

**Example:**
```bash
curl -X POST "http://localhost:8000/api/workers/celery@worker1/shutdown"
```

**Response:**
```json
{
  "status": "success",
  "message": "Shutdown command sent to celery@worker1"
}
```

#### POST /api/workers/{worker_name}/scale

Scale worker pool up or down.

**Query Parameters:**
- `delta`: Number of processes to add (positive) or remove (negative)

**Example:**
```bash
# Grow pool by 2
curl -X POST "http://localhost:8000/api/workers/celery@worker1/scale?delta=2"

# Shrink pool by 1
curl -X POST "http://localhost:8000/api/workers/celery@worker1/scale?delta=-1"
```

**Response:**
```json
{
  "status": "success",
  "message": "Worker pool grown by 2",
  "worker": "celery@worker1",
  "delta": 2
}
```

#### GET /api/workers/active-tasks

Get currently executing tasks.

**Query Parameters:**
- `worker_name` (optional): Filter by specific worker

**Example:**
```bash
# All active tasks
curl "http://localhost:8000/api/workers/active-tasks"

# Active tasks for specific worker
curl "http://localhost:8000/api/workers/active-tasks?worker_name=celery@worker1"
```

**Response:**
```json
{
  "active_tasks": {
    "celery@worker1": [
      {
        "id": "abc-123-def",
        "name": "myapp.tasks.process_data",
        "args": ["user@example.com"],
        "kwargs": {}
      }
    ]
  }
}
```

#### POST /api/tasks/{task_id}/revoke

Revoke (cancel) a task. Optionally terminate it if it's currently running.

**Query Parameters:**
- `terminate` (optional): If `true`, terminate the task if it's currently running (default: `false`)

**Example:**
```bash
# Revoke a pending task
curl -X POST "http://localhost:8000/api/tasks/abc-123-def/revoke"

# Revoke and terminate a running task
curl -X POST "http://localhost:8000/api/tasks/abc-123-def/revoke?terminate=true"
```

**Response:**
```json
{
  "status": "success",
  "message": "Task abc-123-def has been revoked",
  "terminated": false
}
```

#### POST /api/tasks/{task_id}/retry

Retry a failed or revoked task by creating a new task with the same parameters.

**Example:**
```bash
curl -X POST "http://localhost:8000/api/tasks/abc-123-def/retry"
```

**Response:**
```json
{
  "status": "success",
  "message": "Task abc-123-def has been retried",
  "new_task_id": "def-456-ghi"
}
```

**Note:** Only tasks in `failed`, `revoked`, or `orphaned` state can be retried. Attempting to retry a task in any other state will return an error.

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

### Brokers

taskowl supports any Celery/kombu broker via `CELERY_BROKER_URL`. Examples:

```bash
# RabbitMQ / LavinMQ
export CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//"

# Redis
export CELERY_BROKER_URL="redis://localhost:6379/0"
```

The consumer, worker management, and task actions all use Celery's broker
abstraction, so no code changes are needed when switching brokers. The test
data generator (`scripts/generate_test_data.py`) automatically uses the right
exchange type for the broker (topic for AMQP, fanout for Redis).

## Authentication

taskowl supports optional API key authentication for both the REST API and MCP server. When `API_KEY` is set, all requests must include a valid Bearer token.

### Enabling Authentication

Set the `API_KEY` environment variable:

```bash
export API_KEY="your-secret-key-here"
```

### Using Authentication

**REST API:**

Include the API key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer your-secret-key-here" http://localhost:8000/api/tasks
```

**MCP Server:**

Include the API key in the `Authorization` header:

```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-key-here" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

**OpenCode Configuration:**

Add the `headers` field to your `opencode.json`:

```json
{
  "mcp": {
    "taskowl": {
      "type": "remote",
      "url": "http://localhost:8001/mcp",
      "enabled": true,
      "oauth": false,
      "headers": {
        "Authorization": "Bearer your-secret-key-here"
      }
    }
  }
}
```

### Disabling Authentication

To disable authentication, simply don't set `API_KEY` or set it to an empty string:

```bash
unset API_KEY
# or
export API_KEY=""
```

When authentication is disabled, all endpoints are accessible without an API key.

### Protected Endpoints

When authentication is enabled, the following endpoints require a valid API key:

**REST API:**
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/timeline`
- `GET /api/tasks/summary`
- `GET /api/workers`
- `GET /api/workers/list`
- `GET /api/workers/{worker_name}/stats`
- `POST /api/workers/{worker_name}/shutdown`
- `POST /api/workers/{worker_name}/scale`
- `GET /api/workers/active-tasks`
- `POST /api/tasks/{task_id}/revoke`
- `POST /api/tasks/{task_id}/retry`

**MCP Server:**
- All MCP tool calls

The following endpoints remain accessible without authentication:
- `GET /health` - Health check endpoint
- `GET /` - Root endpoint (app info)

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

### list_orphaned_tasks

List tasks currently considered orphaned (stuck in `STARTED` state whose worker went offline).

**Parameters:**
- `limit` (optional): Max number of tasks to return (default: 100)

**Example:**
```
Which tasks are orphaned?
```

**Calls:** `GET /api/tasks/orphaned`

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

Get status of all Celery workers, derived from the latest events (`online` / `offline` / `unknown` based on `WORKER_OFFLINE_TIMEOUT_SECONDS`).

**Example:**
```
Which workers are online?
```

**Calls:** `GET /api/workers`

### revoke_task

Revoke (cancel) a task. Optionally terminate it if it's currently running.

**Parameters:**
- `task_id`: UUID of the task to revoke
- `terminate` (optional): If `true`, terminate the task if it's currently running (default: `false`)

**Example:**
```
Cancel task abc-123-def
```

**Calls:** `POST /api/tasks/{task_id}/revoke`

### retry_task

Retry a failed or revoked task by creating a new task with the same parameters.

**Parameters:**
- `task_id`: UUID of the task to retry

**Example:**
```
Retry task abc-123-def
```

**Calls:** `POST /api/tasks/{task_id}/retry`

**Note:** Only tasks in `failed` or `revoked` state can be retried.

### list_workers

List all active Celery workers.

**Example:**
```
Which workers are currently online?
```

**Calls:** `GET /api/workers/list`

### get_worker_stats

Get detailed statistics for a specific worker.

**Parameters:**
- `worker_name`: Name of the worker (e.g., 'celery@worker1')

**Example:**
```
Show me stats for worker celery@worker1
```

**Calls:** `GET /api/workers/{worker_name}/stats`

### shutdown_worker

Gracefully shutdown a Celery worker.

**Parameters:**
- `worker_name`: Name of the worker to shutdown

**Example:**
```
Shutdown worker celery@worker1
```

**Calls:** `POST /api/workers/{worker_name}/shutdown`

### scale_worker_pool

Scale a worker's pool size up or down.

**Parameters:**
- `worker_name`: Name of the worker
- `delta`: Number of processes to add (positive) or remove (negative)

**Example:**
```
Increase pool size for celery@worker1 by 2
```

**Calls:** `POST /api/workers/{worker_name}/scale`

### get_active_tasks

Get currently executing tasks.

**Parameters:**
- `worker_name` (optional): Filter by specific worker

**Example:**
```
What tasks are currently running?
```

**Calls:** `GET /api/workers/active-tasks`

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
