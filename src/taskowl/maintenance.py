"""Retention/pruning for the append-only event tables.

The event log grows without bound by design; these helpers let operators bound
it by age. Pruning is opt-in: every retention window defaults to ``0`` (keep
forever). Rows are deleted in bounded batches to avoid long table locks and WAL
bloat.

Retention is measured against the event's own ``timestamp`` (event time) for
``task_events`` / ``worker_events`` and against ``created_at`` for
``automation_runs`` (which has no event timestamp). This reuses the existing
``timestamp`` indexes.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskowl.config import settings
from taskowl.database import async_session_maker
from taskowl.models import AutomationRun, TaskEvent, WorkerEvent

logger = logging.getLogger(__name__)


async def _prune_table(
    session: AsyncSession,
    model: type[Any],
    time_column: Any,
    cutoff: datetime,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Delete rows older than ``cutoff`` in batches, or count them in dry-run.

    Returns the number of rows deleted (or that would be deleted).
    """
    if dry_run:
        stmt = select(func.count()).select_from(model).where(time_column < cutoff)
        return int((await session.execute(stmt)).scalar() or 0)

    total = 0
    while True:
        batch_ids = (
            select(model.id).where(time_column < cutoff).order_by(model.id).limit(batch_size)
        )
        result = cast(
            CursorResult, await session.execute(delete(model).where(model.id.in_(batch_ids)))
        )
        await session.commit()
        deleted = result.rowcount or 0
        total += deleted
        if deleted < batch_size:
            break
        # Yield control between batches so long prunes stay responsive.
        await asyncio.sleep(0)
    return total


async def prune_events(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
    batch_size: int | None = None,
    event_retention_days: int | None = None,
    automation_run_retention_days: int | None = None,
) -> dict[str, int]:
    """Prune event tables according to the configured retention windows.

    Args:
        session: Database session to run the deletes on.
        now: Override "now" (useful for tests and one-off backfills).
        dry_run: When True, count rows that would be deleted without deleting.
        batch_size: Rows per delete batch (defaults to ``RETENTION_BATCH_SIZE``).
        event_retention_days: Override ``EVENT_RETENTION_DAYS`` for this run.
        automation_run_retention_days: Override ``AUTOMATION_RUN_RETENTION_DAYS``.

    Returns:
        Mapping of table name to rows deleted (or that would be deleted).
    """
    moment = now or datetime.now(UTC)
    batch = batch_size or settings.retention_batch_size
    event_days = (
        settings.event_retention_days if event_retention_days is None else event_retention_days
    )
    auto_days = (
        settings.automation_run_retention_days
        if automation_run_retention_days is None
        else automation_run_retention_days
    )

    counts = {"task_events": 0, "worker_events": 0, "automation_runs": 0}

    if event_days > 0:
        cutoff = moment - timedelta(days=event_days)
        counts["task_events"] = await _prune_table(
            session, TaskEvent, TaskEvent.timestamp, cutoff, batch, dry_run
        )
        counts["worker_events"] = await _prune_table(
            session, WorkerEvent, WorkerEvent.timestamp, cutoff, batch, dry_run
        )

    if auto_days > 0:
        cutoff = moment - timedelta(days=auto_days)
        counts["automation_runs"] = await _prune_table(
            session, AutomationRun, AutomationRun.created_at, cutoff, batch, dry_run
        )

    return counts


async def run_prune(
    *,
    now: datetime | None = None,
    dry_run: bool = False,
    batch_size: int | None = None,
    event_retention_days: int | None = None,
    automation_run_retention_days: int | None = None,
) -> dict[str, int]:
    """Open a session and run :func:`prune_events` once."""
    async with async_session_maker() as session:
        return await prune_events(
            session,
            now=now,
            dry_run=dry_run,
            batch_size=batch_size,
            event_retention_days=event_retention_days,
            automation_run_retention_days=automation_run_retention_days,
        )
