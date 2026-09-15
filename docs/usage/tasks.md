# Tasks

Query and inspect Celery tasks reconstructed from the append-only event log.

## list_tasks

List tasks with optional filters.

| Parameter | Description |
|---|---|
| `state` | Filter by state (`received`, `started`, `succeeded`, `failed`, `retried`, `revoked`) |
| `name` | Filter by **exact** task name |
| `worker` | Filter by worker hostname |
| `since` | Only tasks created after this datetime (ISO 8601) |
| `search` | Partial, case-insensitive match on the task name |
| `offset` | Number of tasks to skip (pagination) |
| `sort_by` | `timestamp` (default, newest-first), `name`, `state`, `worker` |
| `limit` | Max number of tasks to return (default: 100) |

```bash
# Failed tasks from the last hour, newest first
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/tasks?state=failed&since=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S)"

# Search for a task type by partial name
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/tasks?search=payments"
```

## get_task

Get detailed information about a specific task, including all of its events and
its current state, worker, orphan status, and result.

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/tasks/<task-id>
```

## get_task_timeline

Get all events for a task in chronological order — the full execution flow
(sent, received, started, succeeded/failed, ...).

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/tasks/<task-id>/timeline
```

## get_task_chain

Get the full retry chain for a task: the original task plus every retry,
ordered chronologically, with parent linkage.

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/tasks/<task-id>/chain
```

## get_task_summary

Aggregate task statistics over a time window: total tasks, breakdown by state,
and average runtime of succeeded tasks.

```bash
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/tasks/summary?hours=1"
```

## list_task_types

List distinct task names (types) with a count of how many tasks each has run.

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/tasks/types
```

## list_orphaned_tasks

List tasks stuck in `STARTED` whose worker went offline (crashed / network
drop) before sending a completion event. A task is orphaned when it has been in
`STARTED` longer than `ORPHAN_GRACE_SECONDS` and its worker is offline per
`WORKER_OFFLINE_TIMEOUT_SECONDS`.

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/tasks/orphaned
```