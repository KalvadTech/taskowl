"""event sourcing schema

Revision ID: 002_event_sourcing
Revises: 001_initial
Create Date: 2026-08-07 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_event_sourcing"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create event sourcing schema."""
    # Drop old tables
    op.drop_table("workers")
    op.drop_table("tasks")

    # Create task_events table
    op.create_table(
        "task_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=True),
        # Event-specific fields
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("args", sa.JSON, nullable=True),
        sa.Column("kwargs", sa.JSON, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("exception", sa.Text, nullable=True),
        sa.Column("traceback", sa.Text, nullable=True),
        sa.Column("runtime", sa.Float, nullable=True),
        sa.Column("retries", sa.Integer, nullable=True),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue", sa.String(255), nullable=True),
        sa.Column("root_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pid", sa.Integer, nullable=True),
        sa.Column("signum", sa.Integer, nullable=True),
        sa.Column("terminated", sa.Boolean, nullable=True),
        sa.Column("expired", sa.Boolean, nullable=True),
        sa.Column("requeue", sa.Boolean, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Create indexes for task_events
    op.create_index("idx_task_events_task_id_timestamp", "task_events", ["task_id", "timestamp"])
    op.create_index(
        "idx_task_events_event_type_timestamp", "task_events", ["event_type", "timestamp"]
    )
    op.create_index("idx_task_events_timestamp", "task_events", ["timestamp"])

    # Create worker_events table
    op.create_table(
        "worker_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        # Heartbeat-specific fields
        sa.Column("active", sa.Integer, nullable=True),
        sa.Column("processed", sa.BigInteger, nullable=True),
        sa.Column("freq", sa.Float, nullable=True),
        sa.Column("sw_ident", sa.String(255), nullable=True),
        sa.Column("sw_ver", sa.String(255), nullable=True),
        sa.Column("sw_sys", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Create indexes for worker_events
    op.create_index(
        "idx_worker_events_hostname_timestamp", "worker_events", ["hostname", "timestamp"]
    )
    op.create_index(
        "idx_worker_events_event_type_timestamp", "worker_events", ["event_type", "timestamp"]
    )
    op.create_index("idx_worker_events_timestamp", "worker_events", ["timestamp"])


def downgrade() -> None:
    """Revert to original schema."""
    # Drop new event tables
    op.drop_table("worker_events")
    op.drop_table("task_events")

    # Recreate original tasks table
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("args", sa.JSON, nullable=True),
        sa.Column("kwargs", sa.JSON, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("traceback", sa.Text, nullable=True),
        sa.Column("worker", sa.String(255), nullable=True),
        sa.Column("queue", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("runtime", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for tasks
    op.create_index("idx_tasks_state", "tasks", ["state"])
    op.create_index("idx_tasks_name", "tasks", ["name"])
    op.create_index("idx_tasks_worker", "tasks", ["worker"])
    op.create_index("idx_tasks_created_at", "tasks", ["created_at"])
    op.create_index("idx_tasks_finished_at", "tasks", ["finished_at"])

    # Recreate original workers table
    op.create_table(
        "workers",
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("pool_size", sa.Integer, nullable=True),
        sa.Column("active_count", sa.Integer, nullable=True),
        sa.Column("processed_count", sa.BigInteger, nullable=True),
        sa.Column("loadavg", sa.JSON, nullable=True),
        sa.Column("last_heartbeat", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("hostname"),
    )
