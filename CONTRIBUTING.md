# Contributing to taskowl

Thank you for your interest in contributing to taskowl! This guide will help you get started.

## Code of Conduct

Please be respectful and constructive in all interactions. We're building a welcoming community.

## Getting Started

See the [README](README.md) **Quick Start** for prerequisites, installation,
environment variables, and how to run the API server, consumer, and MCP server.
Set up your local environment there first, then read the rest of this guide.

## Development Workflow

### Making Changes

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Follow the existing code style
   - Add tests for new functionality
   - Update documentation as needed

3. **Run quality checks**:
   ```bash
   make check  # Runs lint, typecheck, and tests
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add your feature description"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Style

### Python Standards

- **Formatter**: ruff (line length: 100)
- **Type checker**: ty (strict mode)
- **Import sorting**: ruff (isort)
- **Python version**: 3.14+

### Guidelines

1. **Type annotations**: All functions must have type hints
   ```python
   # Good
   def get_task(task_id: str) -> dict:
       ...

   # Bad
   def get_task(task_id):
       ...
   ```

2. **Async/await**: Use async for I/O operations
   ```python
   # Good
   async def fetch_data() -> list[dict]:
       async with session.execute(query) as result:
           return result.fetchall()

   # Bad
   def fetch_data():
       # blocking I/O
   ```

3. **Error handling**: Be explicit about error cases
   ```python
   # Good
   try:
       result = await query()
   except ValueError as e:
       logger.error(f"Invalid input: {e}")
       raise

   # Bad
   try:
       result = await query()
   except:
       pass
   ```

4. **Documentation**: Document public APIs
   ```python
   def complex_function(param: str) -> dict:
       """
       Brief description of what this function does.

       Args:
           param: Description of parameter

       Returns:
           Description of return value

       Raises:
           ValueError: When param is invalid
       """
   ```

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run specific test file
uv run pytest tests/test_queries.py -v
```

### Writing Tests

1. **Test location**: `tests/` directory
2. **Naming**: `test_<module>.py`
3. **Structure**: Use pytest fixtures from `conftest.py`

Example test:
```python
@pytest.mark.asyncio
async def test_list_tasks_with_filter(db_session: AsyncSession):
    """Test list_tasks_query with state filter."""
    # Arrange
    task_id = uuid.uuid4()
    db_session.add(TaskEvent(
        event_type="succeeded",
        task_id=task_id,
        timestamp=datetime.now(UTC),
    ))
    await db_session.commit()

    # Act
    result = await list_tasks_query(state="succeeded", session=db_session)

    # Assert
    assert len(result) == 1
    assert result[0]["id"] == str(task_id)
```

### Test Coverage

- **Queries**: Test all query functions with various inputs
- **API endpoints**: Test all REST endpoints
- **Handlers**: Test event handlers
- **Edge cases**: Empty data, invalid inputs, error conditions

## Pull Request Process

### Before Submitting

1. ✅ All tests pass: `make check`
2. ✅ Code is formatted: `uv run ruff format .`
3. ✅ No linting errors: `uv run ruff check .`
4. ✅ Type checking passes: `uv run ty check src/`
5. ✅ Documentation updated (if needed)
6. ✅ Tests added for new functionality

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested your changes

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] All checks pass
```

### Review Process

1. **Automated checks**: CI must pass
2. **Code review**: At least one approval required
3. **Discussion**: Address all review comments
4. **Merge**: Squash and merge to main

## Getting Help

- **Questions**: Open a discussion on GitHub
- **Bugs**: Open an issue with reproduction steps
- **Features**: Open an issue to discuss before implementing

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
