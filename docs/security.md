# Security

TaskOwl is not merely an observer. It can **operate** your Celery cluster: run
tasks, revoke them, restart pools, shut down workers, and manage automations that
do all of the above. Treat it as a control plane and secure it accordingly.

!!! danger
    Authentication is **optional and off by default**. If `API_KEY` is not set,
    every REST endpoint and the MCP server are open to anyone who can reach
    them. Always set `API_KEY` in any environment that is not a local sandbox.

## Authentication

TaskOwl has a single shared-secret API key, set via the `API_KEY` environment
variable. When set, all requests to the REST API and the MCP server must include:

```http
Authorization: Bearer <API_KEY>
```

- **REST API** - enforced by the `verify_api_key` dependency
  (`src/taskowl/auth.py:19`) on every `/api/*` route.
- **MCP server** - enforced by `AuthMiddleware` (`src/taskowl/auth.py:46`)
  before any MCP request is processed.

When `API_KEY` is **unset**, both layers disable themselves and every request is
allowed. This is convenient for a laptop demo and unacceptable in production.

### Always open endpoints

Regardless of `API_KEY`, these endpoints are unauthenticated:

| Endpoint | Why |
|---|---|
| `/health` | Liveness check for orchestrators |
| `/` | Service metadata |
| `/metrics` | Prometheus scraping (see below) |

## Read-only vs destructive operations

Everything under `/api/*` requires the API key. The distinction below is about
**impact**, not authorization, a leaked key is enough to run any of them.

### Read-only

| Operation | Endpoint |
|---|---|
| List / get / search tasks | `GET /api/tasks`, `GET /api/tasks/{id}` |
| Task types, summary, orphans | `GET /api/tasks/types`, `/summary`, `/orphaned` |
| Task timeline / retry chain | `GET /api/tasks/{id}/timeline`, `/chain` |
| Worker status / stats / list | `GET /api/workers`, `/api/workers/list`, `/{name}/stats` |
| Active / scheduled / reserved tasks | `GET /api/workers/active-tasks`, `/scheduled`, `/reserved` |
| Queues | `GET /api/queues` |
| List / get automations and runs | `GET /api/automations`, `/{id}`, `/{id}/runs`, `/{id}/status` |

!!! note
    Some "read" operations use Celery's control bus to ping workers
    (`list_workers`, `get_worker_stats`, active/scheduled/reserved). They are
    non-mutating but still require live workers to respond.

### Destructive / state-changing

| Operation | Endpoint | Effect |
|---|---|---|
| Revoke a task | `POST /api/tasks/{id}/revoke` | Cancels; `?terminate=true` kills a running task |
| Retry a task | `POST /api/tasks/{id}/retry` | Creates and enqueues a new task |
| Execute a task | `POST /api/tasks/execute` | Runs **any registered task** by name, with arbitrary args |
| Shut down a worker | `POST /api/workers/{name}/shutdown` | Stops a worker after in-flight tasks |
| Scale a worker pool | `POST /api/workers/{name}/scale` | Adds/removes worker processes |
| Restart a worker pool | `POST /api/workers/{name}/restart` | Restarts the pool (optionally reloading modules) |
| Create/update/delete/toggle automation | `POST|PUT|DELETE /api/automations...` | Alters automation behavior, including task execution |

`execute_task` is the sharpest edge: it does not check task registration, and
the MCP tool exposes it directly. An API key holder, human or AI, can invoke any
task the worker knows about. Restrict who holds the key.

## The broker is also a control surface

TaskOwl's worker controls and task sends go through the Celery broker using
`app.control` / `app.send_task`. The API key only protects TaskOwl's HTTP and MCP
interfaces; **anyone with broker access has the same power.** Secure your broker
(credentials, network, vhost ACLs) independently of TaskOwl.

## `/metrics` exposure

`/metrics` is intentionally unauthenticated so Prometheus can scrape it without
the TaskOwl API key. It exposes task names, worker hostnames, and automation IDs.
Only expose it to trusted networks, or place it behind a reverse proxy with
network-level or token-based auth.

## Webhooks and automation definitions

Automation actions can POST to arbitrary URLs:

- `slack_webhook` - sends to a Slack-compatible `webhook_url`.
- `webhook` - sends an arbitrary JSON `payload` to a `url`.

Both support `{event.field}` interpolation resolved at fire time. Treat
automation definitions like secrets:

- Webhook URLs frequently embed credentials (Slack incoming-webhook URLs are
  bearer tokens). Anyone who can read an automation can read its URL.
- Anyone who can `POST /api/automations` can configure TaskOwl to call out to an
  arbitrary endpoint on your behalf. Restrict automation write access.

Use the built-in safety knobs (`cooldown_seconds`, `max_runs_per_window` +
`window_seconds`, `circuit_breaker`) to bound action storms, and review run
history via `GET /api/automations/{id}/runs`.

## Network exposure checklist

- Set `API_KEY` everywhere except disposable local sandboxes.
- Bind the API (`TASKOWL_HOST`) and MCP (`MCP_HOST`) servers to private
  interfaces, or front them with a reverse proxy that terminates TLS.
- Do not expose `/metrics` publicly.
- Secure PostgreSQL and the broker; both grant control-level access.
- Rotate `API_KEY` like any other credential, and audit who can reach the
  automation and task-action endpoints.

## See also

- [Configuration](setup/configuration.md) - `API_KEY` and related variables.
- [Task Actions](usage/task-actions.md) - the destructive task operations.
- [Automations](usage/automations.md) - actions and safety controls.
- [Metrics](usage/metrics.md) - the unauthenticated metrics endpoint.
