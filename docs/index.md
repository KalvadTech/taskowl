# TaskOwl

Modern Celery task monitoring with MCP integration. No UI, just data.

TaskOwl watches your Celery cluster's **event stream**, stores every event in
PostgreSQL as an append-only audit log, and exposes that data — plus task,
worker, and queue operations — through a REST API and a set of MCP tools for
LLM-driven monitoring and management.

New here? Start with [Why TaskOwl?](why-taskowl.md).

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
Celery workers
      │
      │ events
      ▼
   Broker
      │
      ▼
 TaskOwl Consumer
      │
      ▼
 PostgreSQL
      │
      ├── REST API
      │
      ├── Prometheus
      │
      └── MCP
            │
            ▼
       AI assistant
```

- **Consumer** (separate process) captures Celery events and appends them to
  PostgreSQL (`task_events`, `worker_events`, `automation_runs`).
- **REST API** serves queries and actions over the event-sourcing tables.
- **MCP server** is a thin wrapper that calls the REST API for LLM access.

## Get started

Jump into the [Installation](setup/installation.md) guide to run TaskOwl, or head
straight to the [Usage Guide](usage/index.md) for the MCP tools and REST API.

!!! note
    TaskOwl only sees what your Celery workers emit. Make sure
    [events are enabled](usage/celery-app.md) — otherwise TaskOwl sees nothing.

!!! warning
    TaskOwl can operate your cluster, not just observe it. Read the
    [Security](security.md) page before exposing it to a network.
