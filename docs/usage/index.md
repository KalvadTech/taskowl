# Usage Guide

This guide walks through everything you can do with taskowl: querying tasks,
managing workers, inspecting queues, and building workflow automations.

## Available MCP tools

| Category | Tools |
|---|---|
| **Tasks** | `list_tasks`, `get_task`, `get_task_timeline`, `get_task_chain`, `get_task_summary`, `list_task_types`, `list_orphaned_tasks` |
| **Task actions** | `revoke_task`, `retry_task`, `execute_task` |
| **Workers** | `get_worker_status`, `list_workers`, `get_worker_stats`, `shutdown_worker`, `scale_worker_pool`, `restart_worker_pool`, `get_active_tasks`, `get_scheduled_tasks`, `get_reserved_tasks` |
| **Queues** | `list_queues` |
| **Automations** | `list_automations`, `create_automation`, `get_automation`, `update_automation`, `delete_automation`, `toggle_automation`, `get_automation_runs`, `get_automation_status` |

**Total: 28 tools** — every tool thin-wraps a REST API endpoint, so anything you
can do via MCP you can also do with `curl` against the API.

## Example questions

Once your MCP client is connected, you can ask:

| Question | Tools used |
|---|---|
| "Show me failed tasks from the last hour" | `list_tasks` |
| "Which task types are running?" | `list_task_types` |
| "Which tasks are orphaned?" | `list_orphaned_tasks` |
| "Show me the timeline for task abc" | `get_task_timeline` |
| "What's the retry chain for task abc?" | `get_task_chain` |
| "What's the task success rate in the last 30 minutes?" | `get_task_summary` |
| "Which workers are online?" | `get_worker_status`, `list_workers` |
| "How many messages are in each queue?" | `list_queues` |
| "Shutdown worker celery@worker1" | `shutdown_worker` |
| "Restart the pool on celery@worker1" | `restart_worker_pool` |
| "What's scheduled to run next?" | `get_scheduled_tasks`, `get_reserved_tasks` |
| "Retry task abc" | `retry_task` |
| "Run myapp.tasks.process now" | `execute_task` |
| "Create an automation that alerts on payment failures" | `create_automation` |

## Structure

- [Configuring Celery](celery-app.md) — make taskowl see your tasks and workers
- [MCP Clients](mcp-clients.md) — connect opencode or any MCP client
- [Tasks](tasks.md) — query tasks, filters, timelines, chains, summaries, orphans
- [Task Actions](task-actions.md) — revoke, retry, execute
- [Workers](workers.md) — status, stats, scale, restart, shutdown, scheduled/reserved
- [Queues](queues.md) — broker queue lengths and consumer counts
- [Automations](automations.md) — declarative trigger → conditions → actions engine
- [Metrics](metrics.md) — Prometheus telemetry