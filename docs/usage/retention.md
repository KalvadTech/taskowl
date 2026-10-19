# Retention

TaskOwl stores every Celery event in PostgreSQL as an append-only log. That is
what makes task history, retry chains, and audits possible, but it also means
the database grows without bound unless you prune it.

Retention is **opt-in**: all retention windows default to `0`, which keeps
everything forever (the 0.1.0 behavior).

## Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `EVENT_RETENTION_DAYS` | Delete `task_events` and `worker_events` older than this many days | `0` (keep forever) |
| `AUTOMATION_RUN_RETENTION_DAYS` | Delete `automation_runs` older than this many days | `0` (keep forever) |
| `RETENTION_CHECK_SECONDS` | How often the consumer runs a prune pass | `3600` |
| `RETENTION_BATCH_SIZE` | Rows deleted per batch | `10000` |

```bash
# Keep 14 days of task/worker events and 30 days of automation runs.
export EVENT_RETENTION_DAYS=14
export AUTOMATION_RUN_RETENTION_DAYS=30
```

Retention for events is measured against each event's own `timestamp` (event
time), which reuses the existing `timestamp` indexes. Because that clock comes
from the workers, a worker with a badly skewed clock can have its rows pruned
earlier or later than you expect. Automation runs have no event timestamp and
are measured against `created_at` (ingestion time).

## How pruning runs

Pruning runs in the consumer on a timer (`RETENTION_CHECK_SECONDS`). When a
retention window is enabled, each pass deletes expired rows in bounded batches
(`RETENTION_BATCH_SIZE`) rather than one large `DELETE`, which keeps table
locks short and avoids WAL bloat. If both retention windows are `0`, the
consumer logs that pruning is disabled and does no work.

Deleted rows leave dead tuples behind; PostgreSQL reclaims them on the next
autovacuum, as usual. Nothing else is required.

## Manual pruning

`taskowl-prune` runs a single prune pass and exits. It is useful for cron-based
scheduling or one-off cleanups.

```bash
# Report how many rows would be deleted, without deleting anything.
taskowl-prune --dry-run

# Delete according to the configured windows.
taskowl-prune

# One-off override, regardless of EVENT_RETENTION_DAYS.
taskowl-prune --days 7
```

Running it from an external scheduler instead of the consumer is fine — just
point it at the same database. Only one prune should be needed per window;
overlapping runs are safe but redundant.

## Duplicate events

Celery events are delivered at-least-once, so a broker redelivery or a consumer
restart can re-send an event TaskOwl has already stored. Every event row carries
a deterministic `dedupe_key`, and ingest uses `INSERT ... ON CONFLICT DO
NOTHING`, so the same event never produces a second row.

Two caveats:

- The key is derived from the event's type, task/host, and **emitted
  timestamp**. An event re-emitted with a *different* timestamp is not
  deduplicated. Deduplication reduces duplicates; it does not guarantee
  exactly-once delivery.
- Events emitted without a timestamp cannot be keyed deterministically. They
  are stored with a NULL key and are always inserted.

## Sizing

Row size depends on your task payloads (arguments, results, tracebacks). If you
are unsure, start with a generous `EVENT_RETENTION_DAYS` and monitor the table
sizes:

```sql
SELECT pg_size_pretty(pg_total_relation_size('task_events'));
SELECT pg_size_pretty(pg_total_relation_size('worker_events'));
```

High-frequency worker heartbeats are usually the first thing to cut back; they
are the highest-volume event type and rarely need long retention.
