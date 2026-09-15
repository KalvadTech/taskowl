# Task Actions

Write operations on tasks. All require authentication (`API_KEY`) and follow
the pattern `actions.py → main.py → mcp/tools.py`.

## revoke_task

Revoke (cancel) a task. Optionally terminate it if it is currently running.

| Parameter | Description |
|---|---|
| `task_id` | UUID of the task to revoke |
| `terminate` | If `true`, terminate the task if it's currently running |

```bash
curl -X POST -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/tasks/<task-id>/revoke?terminate=true"
```

## retry_task

Retry a failed, revoked, or orphaned task by creating a new task with the same
parameters. The retry chain is preserved via `root_id`/`parent_id`, so
`get_task_chain` shows the full retry family.

```bash
curl -X POST -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/tasks/<task-id>/retry
```

## execute_task

Execute a task by name — the Flower "send-task" equivalent. You provide the task
name, args, kwargs, and scheduling options directly; no prior task is needed.

| Parameter | Description |
|---|---|
| `name` | Task name (e.g. `myapp.tasks.process`) |
| `args` | Positional arguments (JSON array) |
| `kwargs` | Keyword arguments (JSON object) |
| `queue` | Queue to send to (defaults to app default) |
| `countdown` | Seconds to wait before the task runs |
| `eta` | ISO 8601 datetime before which the task should not run |
| `expires` | ISO 8601 datetime after which the task expires |
| `priority` | Queue priority (0-9, broker-dependent) |

```bash
curl -X POST -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/tasks/execute \
  -d '{"name": "myapp.tasks.process", "kwargs": {"id": 42}, "queue": "high"}'
```

!!! note
    `execute_task` does not check task registration — the worker surfaces a
    `NotRegistered` error if the name is unknown.