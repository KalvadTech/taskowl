# REST API Refactoring Summary

## Overview

This document summarizes the architectural refactoring performed to separate the REST API from the MCP server, addressing the concern that `make api` should serve REST endpoints while `make mcp` should call those endpoints.

## Problem Statement

Previously, the architecture had issues:
- `make api` only served health check and root endpoints
- `make mcp` directly queried the database
- No separation of concerns
- Other clients couldn't access the data via REST API

## Solution

Implemented a clean three-tier architecture:

```
LLM → MCP Server (port 8001) → REST API (port 8000) → Database
```

## Changes Made

### 1. Created `src/taskowl/queries.py`
- Extracted all database query logic into reusable async functions
- Functions return plain dictionaries for easy serialization
- Functions:
  - `list_tasks_query()` - List tasks with filters
  - `get_task_query()` - Get task details with all events
  - `get_task_timeline_query()` - Get chronological task events
  - `get_task_summary_query()` - Get aggregate statistics
  - `get_worker_status_query()` - Get worker status

### 2. Updated `src/taskowl/main.py`
- Added REST API endpoints:
  - `GET /api/tasks` - List tasks with query parameters
  - `GET /api/tasks/{task_id}` - Get task details
  - `GET /api/tasks/{task_id}/timeline` - Get task timeline
  - `GET /api/tasks/summary` - Get task summary
  - `GET /api/workers` - Get worker status
- Added Pydantic models for response validation
- Added proper error handling with HTTPException

### 3. Refactored `src/taskowl/mcp/tools.py`
- Removed direct database queries
- MCP tools now call REST API endpoints via HTTP using `httpx`
- Each tool makes HTTP request to corresponding REST endpoint
- Simplified code - no more SQLAlchemy imports in MCP tools

### 4. Updated Configuration
- Added `MCP_HOST` and `MCP_PORT` to config
- Updated `.env.example` with new variables
- MCP server runs on port 8001 by default
- REST API runs on port 8000 by default

### 5. Updated Documentation
- Updated README.md with REST API documentation
- Added curl examples for each endpoint
- Updated architecture diagram
- Documented the relationship between MCP tools and REST endpoints
- Updated PLAN.md with Phase 3 completion details

## Benefits

1. **Separation of Concerns**: REST API handles data access, MCP is a thin wrapper
2. **Reusability**: Other clients can use the REST API directly
3. **Testability**: REST API can be tested independently
4. **Maintainability**: Query logic is centralized in one place
5. **Flexibility**: Can add caching, authentication, rate limiting at API layer
6. **Standards Compliance**: REST API follows HTTP conventions

## Testing

All quality checks pass:
- ✅ Ruff linting
- ✅ Ruff formatting
- ✅ Ty type checking
- ✅ Pytest tests

## Usage

### Start Services

```bash
# Terminal 1: Start REST API
make api

# Terminal 2: Start MCP server
make mcp

# Terminal 3: Start consumer
make consume
```

### Test REST API Directly

```bash
# List tasks
curl http://localhost:8000/api/tasks

# Get task details
curl http://localhost:8000/api/tasks/{task_id}

# Get task timeline
curl http://localhost:8000/api/tasks/{task_id}/timeline

# Get task summary
curl http://localhost:8000/api/tasks/summary?hours=1

# Get worker status
curl http://localhost:8000/api/workers
```

### Use MCP Tools

Connect your MCP client to `http://localhost:8001/mcp` and use the tools:
- `list_tasks`
- `get_task`
- `get_task_timeline`
- `get_task_summary`
- `get_worker_status`

## Migration Notes

If you were using the previous version:
1. Update your environment variables (add MCP_HOST and MCP_PORT if needed)
2. Restart all services
3. MCP tools now work by calling the REST API
4. You can now also use the REST API directly from other clients

## Future Enhancements

With this architecture in place, we can now easily add:
- Authentication/authorization at the API layer
- Caching for frequently accessed data
- Rate limiting
- API versioning
- OpenAPI/Swagger documentation (already available at /docs)
- Additional API endpoints without affecting MCP tools
