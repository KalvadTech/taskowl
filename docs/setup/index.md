# Setup

taskowl runs as three separate processes that share a PostgreSQL database and a
Celery broker:

- **API** — FastAPI REST server (default port `8000`)
- **Consumer** — captures Celery events from the broker and stores them
- **MCP** — MCP server exposing the tools to LLMs (default port `8001`)

Follow the [Installation](installation.md) guide to get started, then read
[Configuration](configuration.md) for the full list of environment variables.