"""workflow automations schema

Revision ID: 003_workflow_automations
Revises: 002_event_sourcing
Create Date: 2026-09-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_workflow_automations"
down_revision: str | None = "002_event_sourcing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create automation tables."""
    op.create_table(
        "automations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=True),
        sa.Column("schedule_seconds", sa.Integer, nullable=True),
        sa.Column("conditions", sa.JSON, nullable=True),
        sa.Column("actions", sa.JSON, nullable=True),
        sa.Column("cooldown_seconds", sa.Integer, nullable=True),
        sa.Column("max_runs_per_window", sa.Integer, nullable=True),
        sa.Column("window_seconds", sa.Integer, nullable=True),
        sa.Column("circuit_breaker", sa.JSON, nullable=True),
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
    )
    op.create_index("idx_automations_enabled", "automations", ["enabled"])
    op.create_index("idx_automations_trigger", "automations", ["trigger_type"])

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("automation_id", sa.Integer, nullable=False),
        sa.Column("trigger", sa.String(50), nullable=False),
        sa.Column("matched", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "conditions_passed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("actions_fired", sa.JSON, nullable=True),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_automation_runs_automation_id", "automation_runs", ["automation_id"])
    op.create_index("idx_automation_runs_created_at", "automation_runs", ["created_at"])


def downgrade() -> None:
    """Drop automation tables."""
    op.drop_index("idx_automation_runs_created_at", table_name="automation_runs")
    op.drop_index("idx_automation_runs_automation_id", table_name="automation_runs")
    op.drop_table("automation_runs")
    op.drop_index("idx_automations_trigger", table_name="automations")
    op.drop_index("idx_automations_enabled", table_name="automations")
    op.drop_table("automations")
