# taskowl - Implementation Plan

## Project Overview

**taskowl** is a modern, MCP-first Celery task monitoring tool that provides real-time visibility into Celery task queues without the overhead of a traditional web UI.

### Core Philosophy
- **MCP-first**: Primary interface is via Model Context Protocol, enabling LLM integration
- **Shaper integration**: Use Shaper for dashboards (write SQL, get visualizations)
- **No custom UI**: Avoid maintaining a frontend stack
- **Modern stack**: Python 3.14, FastAPI, uv, async everything
- **Production-ready**: PostgreSQL only, no SQLite fallback complexity

### Target Users
- Developers debugging Celery tasks
- DevOps teams monitoring production Celery clusters
- Teams using AI coding assistants (Claude, Cursor, etc.)

## Architecture

```
┌─────────────────┐
│  RabbitMQ       │◄─────── Celery workers publish events
│  (Broker)       │
└────────┬────────┘
         │
         │ Consume events
         ▼
┌─────────────────┐
│  taskowl        │
│  consumer       │
│  (separate      │
│   process)      │
└────────┬────────┘
         │
         │ Store events (append-only)
         ▼
┌─────────────────┐         ┌─────────────────┐
│  PostgreSQL     │◄────────│  Shaper         │
│  (Event log)    │         │  (Dashboards)   │
└────────┬────────┘         └─────────────────┘
         │
         │ Query
         ▼
┌─────────────────┐
│  FastAPI        │
│  REST API       │
│  (port 8000)    │
└────────┬────────┘
         │
         │ HTTP calls
         ▼
┌─────────────────┐
│  MCP Server     │
│  (port 8001)    │
└────────┬────────┘
         │
         │ MCP protocol
         │
    ┌────┴────┐
    │  LLM    │
    │ (Claude)│
    └─────────┘
```

## Implementation Phases

### Phase 1: Project Skeleton ✅ COMPLETE
**Goal**: Minimal FastAPI app with database connection and MCP tools

**Tasks**:
- [x] Initialize project structure with `uv`
- [x] Create `pyproject.toml` with dependencies
- [x] Set up FastAPI app with health check endpoint
- [x] Configure PostgreSQL connection with SQLAlchemy 2.0 async
- [x] Create Alembic migration for initial schema
- [x] Implement MCP server with HTTP transport (streamable-http)
- [x] Implement MCP tools: `list_tasks`, `get_task`, `get_task_summary`, `get_worker_status`
- [x] Add basic README with setup instructions
- [x] Set up GitHub CI workflow
- [x] Add Makefile for common commands
- [x] Configure ty for type checking

**Deliverables**:
- Working FastAPI app with REST API endpoints
- Database migrations
- Five functional MCP tools
- Basic documentation
- CI pipeline
- Makefile for development

**Notes**:
- MCP server runs as a separate process on port 8001
- FastAPI serves REST API on port 8000
- MCP tools call REST API endpoints via HTTP
- All quality checks pass: ruff, ty, pytest

### Phase 2: Celery Event Consumer ✅ COMPLETE
**Goal**: Capture real-time Celery events and store in database using event sourcing

**Tasks**:
- [x] Implement Celery event consumer using `celery.events.EventReceiver`
- [x] Map Celery events to database models (event sourcing approach)
- [x] Handle task events (sent, received, started, succeeded, failed, revoked, retried, rejected)
- [x] Handle worker events (worker-online, worker-offline, worker-heartbeat)
- [x] Create separate consumer process with CLI (`taskowl-consume`)
- [x] Add error handling and reconnection logic
- [x] Update MCP tools to reconstruct state from events
- [x] Add `get_task_timeline` MCP tool for timeline visualization
- [x] Create database migration for event tables
- [x] Test event handlers and state reconstruction

**Deliverables**:
- Separate consumer process (`taskowl-consume`)
- Append-only event log (task_events, worker_events tables)
- Event handlers for all Celery event types
- State reconstruction in MCP tools
- Timeline visualization capability
- Complete audit trail
- Test data generator script for validation

**Notes**:
- Event sourcing approach: no UPDATE operations, only INSERT
- State is reconstructed from latest events using DISTINCT ON queries
- Complete timeline available for each task
- Better for debugging and analysis than traditional state tables
- Test data generator publishes realistic events to RabbitMQ for end-to-end testing

### Phase 3: REST API & MCP Refactoring ✅ COMPLETE
**Goal**: Separate concerns - REST API for data access, MCP as a thin wrapper

**Tasks**:
- [x] Extract query logic into reusable functions (`queries.py`)
- [x] Implement REST API endpoints in FastAPI:
  - `GET /api/tasks` - list tasks with filters
  - `GET /api/tasks/{task_id}` - get task details
  - `GET /api/tasks/{task_id}/timeline` - get task timeline
  - `GET /api/tasks/summary` - get aggregate statistics
  - `GET /api/workers` - get worker status
- [x] Refactor MCP tools to call REST API endpoints via HTTP
- [x] Add Pydantic models for API responses
- [x] Update documentation with REST API reference
- [x] Test all MCP tools with new architecture

**Deliverables**:
- REST API with 5 endpoints
- MCP tools that call REST API
- Separation of concerns (API handles data, MCP is thin wrapper)
- Updated documentation
- All quality checks pass

**Notes**:
- REST API runs on port 8000 (FastAPI)
- MCP server runs on port 8001 (separate process)
- MCP tools use httpx to call REST API
- Other clients can now use the REST API directly
- Better testability and maintainability

### Phase 4: Shaper Integration & Docs ✅ COMPLETE
**Goal**: Enable dashboard creation and comprehensive documentation

**Tasks**:
- [x] Document database schema for Shaper users
- [x] Create example SQL queries for common dashboards
- [x] Write comprehensive README
- [x] Add troubleshooting section
- [x] Create CONTRIBUTING.md

**Deliverables**:
- Shaper integration guide
- Complete documentation
- Example dashboards
- Troubleshooting guide
- Contributing guidelines

## Technical Specifications

### Tech Stack
- **Python 3.14** (latest stable)
- **FastAPI** (async web framework)
- **uv** (modern package manager, replaces Poetry)
- **SQLAlchemy 2.0** (async ORM)
- **Alembic** (database migrations)
- **asyncpg** (async PostgreSQL driver)
- **MCP SDK** (official Python MCP implementation)
- **Celery** (event consumer)

### Database Schema

taskowl uses an **event sourcing** architecture. Instead of storing current state, we store every event that happens. This gives us:
- Complete audit trail
- Ability to reconstruct state at any point in time
- Task timelines showing the full execution flow
- Better debugging and analysis capabilities

#### task_events Table
```sql
CREATE TABLE task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type VARCHAR(50) NOT NULL,  -- sent, received, started, succeeded, failed, revoked, retried, rejected
    task_id UUID NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    hostname VARCHAR(255),
    name VARCHAR(255),
    args JSON,
    kwargs JSON,
    result JSON,
    exception TEXT,
    traceback TEXT,
    runtime FLOAT,
    retries INTEGER,
    eta TIMESTAMP WITH TIME ZONE,
    expires TIMESTAMP WITH TIME ZONE,
    queue VARCHAR(255),
    root_id UUID,
    parent_id UUID,
    pid INTEGER,
    signum INTEGER,
    terminated BOOLEAN,
    expired BOOLEAN,
    requeue BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_task_events_task_id_timestamp ON task_events(task_id, timestamp);
CREATE INDEX idx_task_events_event_type_timestamp ON task_events(event_type, timestamp);
CREATE INDEX idx_task_events_timestamp ON task_events(timestamp);
```

#### worker_events Table
```sql
CREATE TABLE worker_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type VARCHAR(50) NOT NULL,  -- online, heartbeat, offline
    hostname VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    active INTEGER,
    processed BIGINT,
    freq FLOAT,
    sw_ident VARCHAR(255),
    sw_ver VARCHAR(255),
    sw_sys VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_worker_events_hostname_timestamp ON worker_events(hostname, timestamp);
CREATE INDEX idx_worker_events_event_type_timestamp ON worker_events(event_type, timestamp);
CREATE INDEX idx_worker_events_timestamp ON worker_events(timestamp);
```

### MCP Tools API

The MCP server is exposed via HTTP at `/mcp` using streamable-http transport. State is reconstructed from the event log.

#### list_tasks
```python
@server.tool(name="list_tasks", description="List tasks with optional filters")
async def list_tasks(
    state: str | None = None,
    name: str | None = None,
    worker: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List tasks with optional filters. State reconstructed from latest events."""
```

#### get_task
```python
@server.tool(name="get_task", description="Get detailed information about a specific task")
async def get_task(task_id: str) -> dict:
    """Get detailed information about a specific task, including all events."""
```

#### get_task_timeline
```python
@server.tool(
    name="get_task_timeline", description="Get chronological timeline of all events for a task"
)
async def get_task_timeline(task_id: str) -> list[dict]:
    """Get all events for a task in chronological order for timeline visualization."""
```

#### get_task_summary
```python
@server.tool(name="get_task_summary", description="Get aggregate task statistics")
async def get_task_summary(hours: int = 1) -> dict:
    """Get aggregate task statistics reconstructed from latest events."""
```

#### get_worker_status
```python
@server.tool(name="get_worker_status", description="Get status of all Celery workers")
async def get_worker_status() -> list[dict]:
    """Get status of all Celery workers reconstructed from latest events."""
```

### Dependencies

```toml
[project]
name = "taskowl"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "fastapi==0.141.1",
    "uvicorn==0.52.1",
    "sqlalchemy==2.0.51",
    "asyncpg==0.31.0",
    "alembic==1.19.0",
    "celery==5.6.3",
    "mcp==2.0.0",
    "pydantic==2.13.4",
    "pydantic-settings==2.15.0",
]

[dependency-groups]
dev = [
    "pytest==9.1.1",
    "pytest-asyncio==1.4.0",
    "ruff==0.16.1",
    "ty==0.0.69",
    "httpx==0.28.1",
    "aiosqlite==0.22.1",
]
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://localhost:5432/taskowl` | Yes |
| `CELERY_BROKER_URL` | RabbitMQ connection string | `amqp://guest:guest@localhost:5672//` | Yes |
| `TASKOWL_HOST` | FastAPI server host | `0.0.0.0` | No |
| `TASKOWL_PORT` | FastAPI server port | `8000` | No |
| `MCP_HOST` | MCP server host | `0.0.0.0` | No |
| `MCP_PORT` | MCP server port | `8001` | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |

## Success Criteria

**Phase 1**: ✅ COMPLETE - FastAPI app with MCP endpoint, database migrations, 5 MCP tools
**Phase 2**: ✅ COMPLETE - Event consumer with event sourcing, separate process, timeline visualization
**Phase 3**: ✅ COMPLETE - REST API with 5 endpoints, MCP tools refactored to call REST API
**Phase 4**: ✅ COMPLETE - Shaper integration documented, comprehensive README, troubleshooting guide, CONTRIBUTING.md

## Future Enhancements (Post-MVP)

- **Write capabilities**: retry, cancel, revoke tasks via MCP
- **Worker management**: pool scaling, shutdown/restart
- **Alerts**: notify on failures, slow tasks, worker down
- **Multi-broker support**: Redis, SQS
- **Authentication**: API keys for MCP server
- **Metrics export**: Prometheus, OpenTelemetry
- **Task result storage**: optional result backend integration

## License

MIT License - see LICENSE file for details
