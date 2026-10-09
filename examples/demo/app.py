"""A tiny demo Celery app for TaskOwl.

Start a worker with events enabled:

    celery -A examples.demo.app worker -E --loglevel=info

The tasks here are intentionally varied so the event stream (and therefore
TaskOwl's history) has something interesting to show: quick successes, slow
tasks, and a payment task that fails and retries.
"""

import os
import random
import time

from celery import Celery

broker = os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")

app = Celery("taskowl_demo", broker=broker)

app.conf.update(
    task_send_sent_event=True,
    worker_send_task_events=True,
    worker_heartbeat_interval=2,
    task_acks_late=True,
)


@app.task
def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


@app.task
def send_email(to: str) -> str:
    """Pretend to send an email."""
    time.sleep(random.uniform(0.1, 1.0))
    return f"email sent to {to}"


@app.task
def generate_report(days: int) -> dict:
    """Pretend to generate a slow report."""
    time.sleep(random.uniform(1.0, 3.0))
    return {"days": days, "rows": random.randint(100, 5000)}


@app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    max_retries=3,
)
def charge_payment(self, order_id: int, amount: float) -> dict:
    """Pretend to charge a payment; fails intermittently to exercise retries."""
    time.sleep(random.uniform(0.2, 1.5))
    if random.random() < 0.4:
        raise ConnectionError("upstream timeout")
    return {"order_id": order_id, "amount": amount, "status": "captured"}
