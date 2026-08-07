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
│  FastAPI        │
│  Backend        │
│  - Event consumer
│  - REST API
│  - MCP server (HTTP at /mcp)
└────────┬────────┘
         │
         │ Store task data
         ▼
┌─────────────────┐         ┌─────────────────┐
│  PostgreSQL     │◄────────│  Shaper         │
│  (Task history) │         │  (Dashboards)   │
└─────────────────┘         └─────────────────┘
         ▲
         │ Query via MCP (HTTP)
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
- Working FastAPI app with MCP endpoint at `/mcp`
- Database migrations
- Four functional MCP tools
- Basic documentation
- CI pipeline
- Makefile for development

**Notes**:
- MCP server uses HTTP transport (streamable-http) instead of stdio for better compatibility
- MCP is mounted at `/mcp` endpoint in the FastAPI app
- All quality checks pass: ruff, ty, pytest

### Phase 2: Celery Event Consumer
**Goal**: Capture real-time Celery events and store in database

**Tasks**:
- [ ] Implement Celery event consumer using `celery.events.EventReceiver`
- [ ] Map Celery events to database models
- [ ] Handle worker events (worker-online, worker-offline, worker-heartbeat)
- [ ] Test event consumption with sample Celery app
- [ ] Add error handling and reconnection logic

**Deliverables**:
- Real-time event ingestion
- Automatic task state updates
- Worker heartbeat tracking

### Phase 3: Complete MCP Tools ✅ COMPLETE
**Goal**: Full read-only monitoring capabilities

**Tasks**:
- [x] Implement `list_tasks` - retrieve tasks with filters
- [x] Implement `get_task` - retrieve task details
- [x] Implement `get_task_summary` - aggregate statistics
- [x] Implement `get_worker_status` - worker health
- [x] Add filtering capabilities to `list_tasks`
- [x] Test all MCP tools

**Deliverables**:
- Complete MCP server with 4 tools
- All monitoring tools functional
- Ready for LLM integration

### Phase 4: Shaper Integration & Docs
**Goal**: Enable dashboard creation and comprehensive documentation

**Tasks**:
- [ ] Document database schema for Shaper users
- [ ] Create example SQL queries for common dashboards
- [ ] Write comprehensive README
- [ ] Add troubleshooting section
- [ ] Create CONTRIBUTING.md

**Deliverables**:
- Shaper integration guide
- Complete documentation
- Example dashboards

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

#### Tasks Table
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL,  -- PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
    args JSON,
    kwargs JSON,
    result JSON,
    traceback TEXT,
    worker VARCHAR(255),
    queue VARCHAR(255),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    runtime FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_tasks_state ON tasks(state);
CREATE INDEX idx_tasks_name ON tasks(name);
CREATE INDEX idx_tasks_worker ON tasks(worker);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX idx_tasks_finished_at ON tasks(finished_at DESC);
```

#### Workers Table
```sql
CREATE TABLE workers (
    hostname VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50),  -- online, offline
    pool_size INT,
    active_count INT,
    processed_count BIGINT,
    loadavg JSON,
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### MCP Tools API

The MCP server is exposed via HTTP at `/mcp` using streamable-http transport.

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
    """List tasks with optional filters"""
```

#### get_task
```python
@server.tool(name="get_task", description="Get detailed information about a specific task")
async def get_task(task_id: str) -> dict:
    """Get detailed information about a specific task"""
```

#### get_task_summary
```python
@server.tool(name="get_task_summary", description="Get aggregate task statistics")
async def get_task_summary(hours: int = 1) -> dict:
    """Get aggregate task statistics"""
```

#### get_worker_status
```python
@server.tool(name="get_worker_status", description="Get status of all Celery workers")
async def get_worker_status() -> list[dict]:
    """Get status of all Celery workers"""
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
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |

## Success Criteria

**Phase 1**: ✅ COMPLETE - FastAPI app with MCP endpoint, database migrations, 4 MCP tools
**Phase 2**: Celery events are captured and stored in real-time
**Phase 3**: ✅ COMPLETE - All 4 MCP tools implemented and tested
**Phase 4**: Documentation complete, Shaper dashboards possible

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
