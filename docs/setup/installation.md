# Installation

## Prerequisites

- Python 3.14+
- PostgreSQL 14+
- A Celery broker (RabbitMQ, LavinMQ, Redis, ...)
- [uv](https://github.com/astral-sh/uv)

## Install and migrate

```bash
git clone https://github.com/KalvadTech/taskowl.git
cd taskowl
make install

export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/taskowl"
export CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//"

make migrate
```

## Run the three processes

Open three terminals:

```bash
make api       # REST API on :8000
make consume   # Celery event consumer
make mcp       # MCP server on :8001
```

## Docker Compose

taskowl ships a `docker-compose.yml` that runs the API, consumer, and MCP
server alongside PostgreSQL and RabbitMQ:

```bash
docker compose up --build
```

The API is on `http://localhost:8000`, the MCP server on
`http://localhost:8001/mcp`.

## Verify it's working

1. Confirm the consumer connected to the broker:

   ```bash
   make consume 2>&1 | grep "Connected to Celery broker"
   ```

2. Check the API health endpoint:

   ```bash
   curl http://localhost:8000/health
   # {"status":"ok"}
   ```

3. Make sure your [Celery app emits events](../usage/celery-app.md) — without them
   taskowl sees nothing.