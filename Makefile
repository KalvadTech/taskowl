.PHONY: help install api test lint lint-fix typecheck check migrate migrate-create clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

api: ## Run FastAPI server
	uv run taskowl

test: ## Run tests
	uv run pytest tests/ -v

lint: ## Run linters (check only)
	uv run ruff check .
	uv run ruff format --check .

lint-fix: ## Auto-fix linting issues
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Run type checker
	uv run ty check src/

check: lint typecheck test ## Run all quality checks (lint + typecheck + test)

migrate: ## Run database migrations
	uv run alembic upgrade head

migrate-create: ## Create new migration (usage: make migrate-create MSG="description")
	uv run alembic revision --autogenerate -m "$(MSG)"

clean: ## Remove caches and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info/
