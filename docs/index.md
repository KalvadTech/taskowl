# taskowl

Modern Celery task monitoring with MCP integration. No UI, just data.

taskowl watches your Celery cluster's **event stream**, stores every event in
PostgreSQL as an append-only audit log, and exposes that data — plus task,
worker, and queue operations — through a REST API and a set of MCP tools for
LLM-driven monitoring and management.

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

## Architecture

```
Celery workers ──events──▶ Broker ──▶ taskowl consumer ──▶ PostgreSQL
                                                              │
                         REST API ◀───────────────────────────┘
                              ▲
                              │ HTTP
                         MCP server ──▶ LLM / MCP client
```

- **Consumer** (separate process) captures Celery events and appends them to
  PostgreSQL (`task_events`, `worker_events`, `automation_runs`).
- **REST API** serves queries and actions over the event-sourcing tables.
- **MCP server** is a thin wrapper that calls the REST API for LLM access.

## Get started

Jump into the [Installation](setup/installation.md) guide to run taskowl, or head
straight to the [Usage Guide](usage/index.md) for the MCP tools and REST API.

!!! note
    taskowl only sees what your Celery workers emit. Make sure
    [events are enabled](usage/celery-app.md) — otherwise taskowl sees nothing.