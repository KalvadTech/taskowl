#!/usr/bin/env python3
"""Generate realistic Celery events and publish to RabbitMQ for testing."""

import argparse
import json
import os
import random
import time
import uuid
from datetime import datetime

from kombu import Connection, Exchange

# Realistic task names
TASK_NAMES = [
    "app.tasks.send_email",
    "app.tasks.process_payment",
    "app.tasks.generate_report",
    "app.tasks.sync_data",
    "app.tasks.cleanup",
    "app.tasks.send_notification",
    "app.tasks.process_image",
    "app.tasks.validate_order",
    "app.tasks.update_inventory",
    "app.tasks.generate_invoice",
]

# Queue names
QUEUES = ["default", "high_priority", "low_priority", "email", "reports"]

# Worker hostnames
WORKER_HOSTNAMES = [
    "worker-1@prod-server-01",
    "worker-2@prod-server-01",
    "worker-1@prod-server-02",
    "worker-2@prod-server-02",
    "worker-1@staging-worker-01",
]

# Software info for workers
SW_IDENT = "py-celery"
SW_VER = "5.3.4"
SW_SYS = "Linux"


def generate_task_id() -> str:
    """Generate a random UUID for task ID."""
    return str(uuid.uuid4())


def generate_timestamp() -> float:
    """Generate current timestamp as float."""
    return datetime.now().timestamp()


def generate_task_received_event(task_id: str, task_name: str, queue: str, worker: str) -> dict:
    """Generate a task-received event."""
    return {
        "uuid": task_id,
        "name": task_name,
        "args": json.dumps([random.randint(1, 100)]),
        "kwargs": json.dumps({"user_id": random.randint(1000, 9999)}),
        "retries": 0,
        "eta": None,
        "expires": None,
        "queue": queue,
        "exchange": "",
        "routing_key": queue,
        "root_id": task_id,
        "parent_id": None,
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "type": "task-received",
        "state": "RECEIVED",
    }


def generate_task_started_event(task_id: str, worker: str) -> dict:
    """Generate a task-started event."""
    return {
        "uuid": task_id,
        "pid": random.randint(1000, 9999),
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "type": "task-started",
        "state": "STARTED",
    }


def generate_task_succeeded_event(
    task_id: str, worker: str, runtime: float, slow: bool = False
) -> dict:
    """Generate a task-succeeded event."""
    result = {"status": "success", "data": {"processed": random.randint(1, 1000)}}
    if slow:
        result["note"] = "slow task completed"

    return {
        "uuid": task_id,
        "result": json.dumps(result),
        "runtime": runtime,
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "type": "task-succeeded",
        "state": "SUCCESS",
    }


def generate_task_failed_event(task_id: str, worker: str) -> dict:
    """Generate a task-failed event."""
    exceptions = [
        ("ValueError", "Invalid input data"),
        ("ConnectionError", "Failed to connect to external service"),
        ("TimeoutError", "Operation timed out after 30 seconds"),
        ("KeyError", "Missing required field: user_id"),
        ("RuntimeError", "Unexpected error during processing"),
    ]
    exc_type, exc_msg = random.choice(exceptions)

    return {
        "uuid": task_id,
        "exception": f"{exc_type}({exc_msg})",
        "traceback": f"Traceback (most recent call last):\n"
        f'  File "app/tasks.py", line {random.randint(10, 100)}, in process\n'
        f"    raise {exc_type}('{exc_msg}')\n"
        f"{exc_type}: {exc_msg}",
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "type": "task-failed",
        "state": "FAILURE",
    }


def generate_task_retried_event(task_id: str, worker: str) -> dict:
    """Generate a task-retried event."""
    return {
        "uuid": task_id,
        "exception": "ConnectionError(Temporary connection failure)",
        "traceback": "Traceback (most recent call last):\n"
        '  File "app/tasks.py", line 42, in connect\n'
        "    raise ConnectionError('Temporary connection failure')\n"
        "ConnectionError: Temporary connection failure",
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "type": "task-retried",
        "state": "RETRY",
    }


def generate_worker_online_event(worker: str) -> dict:
    """Generate a worker-online event."""
    return {
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "freq": 2.0,
        "sw_ident": SW_IDENT,
        "sw_ver": SW_VER,
        "sw_sys": SW_SYS,
        "type": "worker-online",
    }


def generate_worker_heartbeat_event(worker: str, active: int = 0, processed: int = 0) -> dict:
    """Generate a worker-heartbeat event."""
    return {
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "freq": 2.0,
        "sw_ident": SW_IDENT,
        "sw_ver": SW_VER,
        "sw_sys": SW_SYS,
        "active": active,
        "processed": processed,
        "type": "worker-heartbeat",
    }


def generate_worker_offline_event(worker: str) -> dict:
    """Generate a worker-offline event."""
    return {
        "hostname": worker,
        "timestamp": generate_timestamp(),
        "freq": 2.0,
        "sw_ident": SW_IDENT,
        "sw_ver": SW_VER,
        "sw_sys": SW_SYS,
        "type": "worker-offline",
    }


def publish_event(connection: Connection, exchange: Exchange, event: dict) -> None:
    """Publish a single event to RabbitMQ."""
    producer = connection.Producer(serializer="json")
    event_type = event["type"]

    # Determine routing key based on event type
    if event_type.startswith("task-"):
        routing_key = "task.#"
    elif event_type.startswith("worker-"):
        routing_key = "worker.#"
    else:
        routing_key = "#"

    producer.publish(
        event,
        exchange=exchange,
        routing_key=routing_key,
        content_type="application/json",
    )


def generate_success_task(connection: Connection, exchange: Exchange, slow: bool = False) -> None:
    """Generate a successful task lifecycle."""
    task_id = generate_task_id()
    task_name = random.choice(TASK_NAMES)
    queue = random.choice(QUEUES)
    worker = random.choice(WORKER_HOSTNAMES)

    # Task received
    event = generate_task_received_event(task_id, task_name, queue, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task started
    event = generate_task_started_event(task_id, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task succeeded
    runtime = random.uniform(10.0, 60.0) if slow else random.uniform(0.1, 5.0)
    event = generate_task_succeeded_event(task_id, worker, runtime, slow)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))


def generate_failure_task(connection: Connection, exchange: Exchange) -> None:
    """Generate a failed task lifecycle."""
    task_id = generate_task_id()
    task_name = random.choice(TASK_NAMES)
    queue = random.choice(QUEUES)
    worker = random.choice(WORKER_HOSTNAMES)

    # Task received
    event = generate_task_received_event(task_id, task_name, queue, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task started
    event = generate_task_started_event(task_id, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task failed
    event = generate_task_failed_event(task_id, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))


def generate_retry_task(connection: Connection, exchange: Exchange) -> None:
    """Generate a task that fails then retries and succeeds."""
    task_id = generate_task_id()
    task_name = random.choice(TASK_NAMES)
    queue = random.choice(QUEUES)
    worker = random.choice(WORKER_HOSTNAMES)

    # Task received
    event = generate_task_received_event(task_id, task_name, queue, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task started (first attempt)
    event = generate_task_started_event(task_id, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task failed
    event = generate_task_failed_event(task_id, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task retried
    event = generate_task_retried_event(task_id, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task started (second attempt)
    event = generate_task_started_event(task_id, worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Task succeeded
    runtime = random.uniform(0.1, 5.0)
    event = generate_task_succeeded_event(task_id, worker, runtime)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))


def generate_worker_lifecycle(connection: Connection, exchange: Exchange, hours: float) -> None:
    """Generate worker online, heartbeat, and offline events."""
    worker = random.choice(WORKER_HOSTNAMES)

    # Worker online
    event = generate_worker_online_event(worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))

    # Generate heartbeats over the time period
    # Assume heartbeat every 2 seconds, but we'll generate a subset
    num_heartbeats = int((hours * 3600) / 2)
    num_heartbeats = min(num_heartbeats, 10)  # Limit to 10 heartbeats for testing

    processed = 0
    for _ in range(num_heartbeats):
        active = random.randint(0, 3)
        processed += random.randint(1, 5)
        event = generate_worker_heartbeat_event(worker, active, processed)
        publish_event(connection, exchange, event)
        time.sleep(random.uniform(0.1, 0.3))

    # Worker offline
    event = generate_worker_offline_event(worker)
    publish_event(connection, exchange, event)
    time.sleep(random.uniform(0.1, 0.3))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate realistic Celery events for testing")
    parser.add_argument(
        "--tasks", type=int, default=50, help="Number of tasks to generate (default: 50)"
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=1.0,
        help="Time range in hours for worker events (default: 1)",
    )
    parser.add_argument(
        "--success",
        type=int,
        default=70,
        help="Percentage of success tasks (default: 70)",
    )
    parser.add_argument(
        "--failure",
        type=int,
        default=20,
        help="Percentage of failure tasks (default: 20)",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=10,
        help="Percentage of retry tasks (default: 10)",
    )
    parser.add_argument(
        "--slow-tasks",
        type=int,
        default=5,
        help="Number of slow tasks (default: 5)",
    )
    parser.add_argument(
        "--broker-url",
        type=str,
        default=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"),
        help="RabbitMQ broker URL (default: from CELERY_BROKER_URL env or amqp://guest:guest@localhost:5672//)",
    )

    args = parser.parse_args()

    # Validate percentages
    total = args.success + args.failure + args.retry
    if total != 100:
        print(f"Error: Percentages must sum to 100 (got {total})")
        return

    print(f"Connecting to RabbitMQ at {args.broker_url}")
    print(f"Generating {args.tasks} tasks...")
    print(f"  - Success: {args.success}% ({int(args.tasks * args.success / 100)} tasks)")
    print(f"  - Failure: {args.failure}% ({int(args.tasks * args.failure / 100)} tasks)")
    print(f"  - Retry: {args.retry}% ({int(args.tasks * args.retry / 100)} tasks)")
    print(f"  - Slow tasks: {args.slow_tasks}")
    print()

    # Connect to RabbitMQ
    with Connection(args.broker_url) as connection:
        # Create celeryev exchange
        exchange = Exchange("celeryev", type="topic", durable=False)

        print("Publishing events (with delays)...")

        # Calculate task distribution
        num_success = int(args.tasks * args.success / 100)
        num_failure = int(args.tasks * args.failure / 100)
        num_retry = int(args.tasks * args.retry / 100)

        # Adjust for slow tasks (they come from success pool)
        num_normal_success = num_success - args.slow_tasks

        total_events = 0

        # Generate success tasks (normal)
        for _ in range(num_normal_success):
            generate_success_task(connection, exchange, slow=False)
            total_events += 3  # received, started, succeeded

        # Generate success tasks (slow)
        for _ in range(args.slow_tasks):
            generate_success_task(connection, exchange, slow=True)
            total_events += 3

        # Generate failure tasks
        for _ in range(num_failure):
            generate_failure_task(connection, exchange)
            total_events += 3

        # Generate retry tasks
        for _ in range(num_retry):
            generate_retry_task(connection, exchange)
            total_events += 7  # received, started, failed, retried, started, succeeded

        # Generate worker lifecycle events
        print("\nGenerating worker lifecycle events...")
        for _ in WORKER_HOSTNAMES:
            generate_worker_lifecycle(connection, exchange, args.hours)
            total_events += 12  # online + ~10 heartbeats + offline

        print(f"\nPublished {total_events} events")
        print("Done! Events are being processed by the consumer.")


if __name__ == "__main__":
    main()
