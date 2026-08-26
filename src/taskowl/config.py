from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: str = Field(
        default="postgresql+asyncpg://localhost:5432/taskowl",
        description="PostgreSQL connection string",
    )
    celery_broker_url: str = Field(
        default="amqp://guest:guest@localhost:5672//",
        description=(
            "Celery broker URL (RabbitMQ, Redis, or other kombu-supported "
            "transport, e.g. amqp://..., redis://...)"
        ),
    )
    taskowl_host: str = Field(
        default="0.0.0.0",
        description="FastAPI server host",
    )
    taskowl_port: int = Field(
        default=8000,
        description="FastAPI server port",
    )
    mcp_host: str = Field(
        default="0.0.0.0",
        description="MCP server host",
    )
    mcp_port: int = Field(
        default=8001,
        description="MCP server port",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for authentication (optional, no auth if not set)",
    )
    orphan_grace_seconds: int = Field(
        default=60,
        description="Wait after task started before flagging as orphan",
    )
    worker_offline_timeout_seconds: int = Field(
        default=30,
        description="No heartbeat for this long means worker is offline",
    )
    alert_webhook_url: str | None = Field(
        default=None,
        description="Slack webhook URL to post alerts to (disabled if not set)",
    )
    alert_on_task_failed: bool = Field(
        default=True,
        description="Enable task-failed alerts",
    )
    alert_on_worker_offline: bool = Field(
        default=True,
        description="Enable worker-offline alerts",
    )
    alert_slow_task_seconds: float | None = Field(
        default=None,
        description="Alert when a succeeded task exceeds this runtime (disabled if None)",
    )
    alert_worker_check_seconds: int = Field(
        default=30,
        description="Interval for the periodic stale-worker check",
    )

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
