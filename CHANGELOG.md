# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Idempotent event ingest: `task_events` and `worker_events` now carry a
  deterministic `dedupe_key` and are written with `INSERT ... ON CONFLICT DO
  NOTHING`, so broker redeliveries and consumer replays no longer create
  duplicate rows. Events emitted without a timestamp keep a NULL key and are
  always inserted.
- Configurable retention for the append-only event log via
  `EVENT_RETENTION_DAYS`, `AUTOMATION_RUN_RETENTION_DAYS`,
  `RETENTION_CHECK_SECONDS`, and `RETENTION_BATCH_SIZE`. Pruning runs in the
  consumer and deletes expired rows in bounded batches; default is to keep
  everything.
- New `taskowl-prune` CLI for one-off or cron-based pruning, with `--dry-run`
  and a `--days` override.

## [0.1.0] - 2026-10-09

Initial release.

### Added

- Celery event consumer that appends task and worker events to PostgreSQL as an
  append-only audit log.
- Async REST API (FastAPI) for querying task history and performing task,
  worker, and queue operations.
- MCP server exposing 28 tools as a thin wrapper over the REST API.
- Event-sourced task state with timelines, retry chains, and orphan detection.
- Task actions: revoke, retry, and execute tasks by name.
- Worker management: list, inspect, scale, restart, and shut down workers.
- Queue monitoring for any kombu broker (message and consumer counts).
- Declarative workflow automations (trigger → conditions → actions) with
  cooldowns, rate limits, and circuit breakers.
- Prometheus metrics at `/metrics`.
- Optional API key authentication for the REST API and MCP server.
- Docker Compose setup with an optional `demo` profile and a bundled demo
  Celery workload.

[Unreleased]: https://github.com/KalvadTech/taskowl/compare/0.1.0...HEAD
[0.1.0]: https://github.com/KalvadTech/taskowl/releases/tag/0.1.0
