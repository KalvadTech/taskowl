# Queues

Inspect the Celery broker's queues. Works with any kombu transport (RabbitMQ,
LavinMQ, Redis) via `CELERY_BROKER_URL`.

## list_queues

Report per-queue message and consumer counts for the declared queues, plus a
`total_messages` aggregate. Queues are ordered by message count descending.

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/queues
```

Example response:

```json
{
  "queues": [
    {"name": "default", "messages": 42, "consumers": 2},
    {"name": "high", "messages": 5, "consumers": 1}
  ],
  "total_messages": 47
}
```

Uses kombu's passive `queue_declare`, so no broker state is modified. If the
broker is unreachable, the endpoint returns a `502`.