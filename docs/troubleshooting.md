# Troubleshooting

## Worker not appearing / no events in the database

1. Verify workers emit events — start with `-E` or set `worker_send_task_events`.
2. Check the consumer connected:

   ```bash
   make consume 2>&1 | grep "Connected to Celery broker"
   ```

3. Verify events reach the broker:

   ```bash
   celery -A your_app events --dump
   ```

4. Check event counts in the database:

   ```sql
   SELECT COUNT(*) FROM task_events;
   SELECT COUNT(*) FROM worker_events;
   ```

## Database connection errors

- `pg_isready` to confirm PostgreSQL is up.
- Check `DATABASE_URL` format: `postgresql+asyncpg://user:pass@host:port/dbname`.
- Verify the role has access to the database.

## Broker connection errors

- `rabbitmqctl status` (or your broker's health check) to confirm it's running.
- Check `CELERY_BROKER_URL` format and credentials.

## Port already in use

- API: `lsof -i :8000` / MCP: `lsof -i :8001`
- Kill the offending process: `kill $(lsof -t -i :8001)`

## Getting help

Open an issue with the error message, environment details, steps to reproduce,
and relevant (sanitized) logs:
https://github.com/KalvadTech/taskowl/issues