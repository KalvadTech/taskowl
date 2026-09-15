# Workers

Inspect and manage Celery workers. Read operations use `app.control.inspect()`;
write operations use `app.control` and require live workers.

## get_worker_status

Derive worker status from the event log: `online` / `offline` / `unknown`,
based on `WORKER_OFFLINE_TIMEOUT_SECONDS`. Includes heartbeat details and the
last event type.

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/workers
```

## list_workers

Ping all workers and list who is alive.

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/workers/list
```

## get_worker_stats

Detailed statistics for a specific worker (requires the worker to respond).

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/workers/celery@worker1/stats
```

## get_active_tasks

Currently executing tasks across all workers, or a specific worker.

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/workers/active-tasks
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/workers/active-tasks?worker_name=celery@worker1"
```

## get_scheduled_tasks

Tasks with an ETA/countdown waiting in workers' queues.

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/workers/scheduled
```

## get_reserved_tasks

Tasks prefetched by a worker but not yet started.

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/workers/reserved
```

## shutdown_worker

Gracefully shut down a worker (waits for current tasks).

```bash
curl -X POST -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/workers/celery@worker1/shutdown
```

## scale_worker_pool

Grow or shrink a worker's pool size.

```bash
# Add 2 processes
curl -X POST -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/workers/celery@worker1/scale?delta=2"
# Remove 1 process
curl -X POST -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/workers/celery@worker1/scale?delta=-1"
```

## restart_worker_pool

Restart a worker's execution pool, optionally reloading modules.

```bash
curl -X POST -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/workers/celery@worker1/restart
# With module reload
curl -X POST -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/workers/celery@worker1/restart?reload=true"
```