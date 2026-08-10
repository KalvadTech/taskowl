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
        description="RabbitMQ connection string",
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

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
