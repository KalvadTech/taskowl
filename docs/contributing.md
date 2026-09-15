# Contributing

Thank you for your interest in contributing to taskowl!

## Development setup

See the [Installation](setup/installation.md) guide to get a local environment
running, then continue here.

## Development workflow

1. **Create a feature branch**:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** — follow the existing code style, add tests, update docs.

3. **Run quality checks**:

   ```bash
   make check  # Runs lint, typecheck, and tests
   ```

4. **Commit and push**, then open a pull request.

## Code style

- **Formatter**: ruff (line length: 100)
- **Type checker**: ty (strict mode)
- **Import sorting**: ruff (isort)
- **Python version**: 3.14+

Guidelines:

- **Type annotations**: All functions must have type hints.
- **Async/await**: Use async for I/O operations.
- **Error handling**: Be explicit about error cases — return `{"error": ...}`
  dicts from core functions, surface them as HTTP 4xx/5xx in the API layer.
- **Documentation**: Document public APIs with docstrings.

## Testing

```bash
# Run all tests
make test

# Run a specific test file
uv run pytest tests/test_queries.py -v
```

Tests live in `tests/`, named `test_<module>.py`, using fixtures from
`conftest.py`.

## Docs

The site is built with MkDocs + Material. Edit pages under `docs/`, then verify
locally:

```bash
make docs         # build the site
make docs-serve   # preview at http://localhost:9000
```

## Pull requests

Before submitting: all tests pass (`make check`), code is formatted
(`uv run ruff format .`), no lint errors, docs updated if needed, and tests added
for new functionality. At least one approval is required; merges are squash
merged to `main`.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.