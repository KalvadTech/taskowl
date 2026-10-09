# Why TaskOwl?

Celery gives you workers and tasks. **TaskOwl gives you observability, history,
control, and an AI interface for the whole cluster.**

Celery's event stream contains a huge amount of useful operational information
(task states, retries, worker heartbeats, queue activity) but once an event has
passed, it is gone. TaskOwl turns that stream into a persistent operational
history and exposes it through REST and MCP.

## Before / after

**Without TaskOwl**

```text
Celery
  ├── workers
  ├── broker
  └── events → mostly ephemeral
```

**With TaskOwl**

```text
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

Celery's events are emitted only if enabled. TaskOwl's consumer subscribes to
that stream, appends every event to PostgreSQL as an append-only log, and
reconstructs current task, worker, and queue state from it. The REST API and the
MCP server are thin read/write interfaces over that same data.

## TaskOwl is not another Flower

Flower is a great real-time Celery monitor, and TaskOwl was inspired by it. But
the two solve different problems. TaskOwl is built around **durable history** and
**programmatic/AI-driven operations**, and deliberately ships **no UI**.

|                             | Flower    | TaskOwl |
| --------------------------- | --------- | ------- |
| Real-time Celery monitoring | ✓         | ✓       |
| Persistent event history    |           | ✓       |
| REST API                    |           | ✓       |
| MCP                         |           | ✓       |
| AI-assisted operations      |           | ✓       |
| Task retry/revoke/execute   | ✓/partial | ✓       |
| Worker management           | ✓         | ✓       |
| Queue monitoring            | ✓         | ✓       |
| Declarative automations     |           | ✓       |
| Prometheus                  |           | ✓       |
| UI required                 | ✓         | **No**  |

If you want a dashboard to click through, use Flower. If you want your Celery
cluster's history and controls available to scripts, automations, and AI agents,
use TaskOwl. They can happily run side by side.

## Design principles

**MCP-first**
The system is designed to be operated programmatically and through AI agents,
not through a GUI.

**PostgreSQL as the source of operational history**
Celery events become durable data rather than transient messages.

**API-first**
MCP is a thin interface over the REST API, so automation and human tooling use
the same capabilities. Everything you can do via MCP you can also do with `curl`.

**No UI**
TaskOwl focuses on exposing operational data and control. Use Grafana, your
existing observability stack, an MCP client, or build your own interface.

**Async throughout**
Built for modern Python deployments.

## What TaskOwl is not

TaskOwl is intentionally scoped. It is not a dashboard, an authentication UI, a
multi-tenant platform, a log aggregator, or a distributed tracing system. Those
are valuable, but they are not this project. **No UI, just data.**

## Next steps

- [Install TaskOwl](setup/installation.md) - the Docker path takes about five minutes.
- [Usage Guide](usage/index.md) - the MCP tools and REST API.
- [Security](security.md) - TaskOwl can operate your cluster, not just observe it.
