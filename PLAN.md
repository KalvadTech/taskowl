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
│  - MCP server
│  - REST API (optional)
└────────┬────────┘
         │
         │ Store task data
         ▼
┌─────────────────┐         ┌─────────────────┐
│  PostgreSQL     │◄────────│  Shaper         │
│  (Task history) │         │  (Dashboards)   │
└─────────────────┘         └─────────────────┘
         ▲
         │ Query via MCP
         │
    ┌────┴────┐
    │  LLM    │
    │ (Claude)│
    └─────────┘
```

## Implementation Phases

### Phase 1: Project Skeleton (Current)
**Goal**: Minimal FastAPI app with database connection and one working MCP tool

**Tasks**:
- [x] Initialize project structure with `uv`
- [x] Create `pyproject.toml` with dependencies
- [x] Set up FastAPI app with health check endpoint
- [x] Configure PostgreSQL connection with SQLAlchemy 2.0 async
- [x] Create Alembic migration for initial schema
- [x] Implement first MCP tool: `list_tasks`
- [x] Add basic README with setup instructions
- [x] Set up GitHub CI workflow

**Deliverables**:
- Working FastAPI app
- Database migrations
- One functional MCP tool
- Basic documentation
- CI pipeline

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

### Phase 3: Complete MCP Tools
**Goal**: Full read-only monitoring capabilities

**Tasks**:
- [ ] Implement `get_task` - retrieve task details
- [ ] Implement `get_task_summary` - aggregate statistics
- [ ] Implement `get_worker_status` - worker health
- [ ] Implement `get_queue_stats` - queue metrics
- [ ] Add filtering capabilities to `list_tasks`
- [ ] Test all MCP tools with Claude

**Deliverables**:
- Complete MCP server
- All monitoring tools functional
- Tested with LLM integration

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
    args JSONB,
    kwargs JSONB,
    result JSONB,
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
    loadavg FLOAT[],
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### MCP Tools API

#### list_tasks
```python
@mcp.tool()
async def list_tasks(
    state: str | None = None,
    name: str | None = None,
    worker: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[Task]:
    """List tasks with optional filters"""
```

#### get_task
```python
@mcp.tool()
async def get_task(task_id: str) -> Task:
    """Get detailed information about a specific task"""
```

#### get_task_summary
```python
@mcp.tool()
async def get_task_summary(since: timedelta = timedelta(hours=1)) -> TaskSummary:
    """Get aggregate task statistics"""
```

#### get_worker_status
```python
@mcp.tool()
async def get_worker_status() -> list[Worker]:
    """Get status of all Celery workers"""
```

#### get_queue_stats
```python
@mcp.tool()
async def get_queue_stats() -> dict[str, QueueStats]:
    """Get queue statistics"""
```

### Dependencies

```toml
[project]
name = "taskowl"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "celery>=5.4.0",
    "mcp>=1.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "httpx>=0.28.0",
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
| `MCP_ENABLED` | Enable MCP server | `true` | No |
| `MCP_HOST` | MCP server host | `0.0.0.0` | No |
| `MCP_PORT` | MCP server port | `8001` | No |

## Success Criteria

**Phase 1**: ✅ Can start FastAPI app, connect to database, query tasks via MCP
**Phase 2**: Celery events are captured and stored in real-time
**Phase 3**: All MCP tools work, can monitor tasks/workers/queues via Claude
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
