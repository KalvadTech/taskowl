# Configuring your Celery app

taskowl listens to Celery's **events** stream, which workers emit only if
enabled. Add this to your Celery application so taskowl can see your tasks and
workers:

```python
# celery_app.py
from celery import Celery

app = Celery("myapp", broker="amqp://guest:guest@localhost:5672//")

# Workers emit task/worker events (sent, received, started, succeeded, failed, ...)
app.conf.worker_send_task_events = True

# Emit a 'task-sent' event when a task is published
app.conf.task_send_sent_event = True

# How often workers send a heartbeat (default: 2s). Higher values
# increase the worker-offline detection delay.
app.conf.worker_heartbeat_interval = 2
```

Alternatively, start your worker with the `-E` flag, which is equivalent to
`worker_send_task_events = True`:

```bash
celery -A myapp worker -E --loglevel=info
```

!!! note
    If events are not enabled, taskowl simply sees nothing — no tasks, no
    workers. Enabling events is the one integration required.