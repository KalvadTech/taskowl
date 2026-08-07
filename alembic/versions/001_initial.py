"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-08-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial schema."""
    # Create tasks table
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("kwargs", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("worker", sa.String(255), nullable=True),
        sa.Column("queue", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("runtime", sa.Float(), nullable=True),
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

    # Create workers table
    op.create_table(
        "workers",
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("pool_size", sa.Integer(), nullable=True),
        sa.Column("active_count", sa.Integer(), nullable=True),
        sa.Column("processed_count", sa.BigInteger(), nullable=True),
        sa.Column("loadavg", sa.JSON(), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(), nullable=True),
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


def downgrade() -> None:
    """Drop initial schema."""
    op.drop_table("workers")
    op.drop_table("tasks")
