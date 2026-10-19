"""event dedupe key

Adds a nullable, unique ``dedupe_key`` to the ``task_events`` and
``worker_events`` tables. The key makes ingest idempotent: broker
redeliveries and consumer replays are dropped with ``ON CONFLICT DO NOTHING``.

The column is nullable so that pre-existing rows (and events emitted without a
timestamp, which cannot be keyed deterministically) never collide — a unique
index allows multiple NULLs on both PostgreSQL and SQLite, so no backfill or
de-duplication of historical rows is required. Because the column is entirely
NULL at migration time, the index build is cheap; very large deployments may
still prefer to build it during a maintenance window (or with
``CREATE UNIQUE INDEX CONCURRENTLY``).

Revision ID: 004_event_dedupe_retention
Revises: 003_workflow_automations
Create Date: 2026-10-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_event_dedupe_retention"
down_revision: str | None = "003_workflow_automations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the dedupe_key column and unique index to the event tables."""
    op.add_column("task_events", sa.Column("dedupe_key", sa.String(64), nullable=True))
    op.add_column("worker_events", sa.Column("dedupe_key", sa.String(64), nullable=True))

    op.create_index("uq_task_events_dedupe_key", "task_events", ["dedupe_key"], unique=True)
    op.create_index("uq_worker_events_dedupe_key", "worker_events", ["dedupe_key"], unique=True)


def downgrade() -> None:
    """Drop the dedupe_key column and unique index from the event tables."""
    op.drop_index("uq_worker_events_dedupe_key", table_name="worker_events")
    op.drop_index("uq_task_events_dedupe_key", table_name="task_events")

    op.drop_column("worker_events", "dedupe_key")
    op.drop_column("task_events", "dedupe_key")
