"""Continuously produce demo tasks for the TaskOwl demo.

Run it alongside ``examples.demo.app``:

    python -m examples.demo.producer
"""

import random
import time

from examples.demo.app import add, charge_payment, generate_report, send_email


def main() -> None:
    """Send a steady stream of demo tasks."""
    order_id = 1000
    while True:
        add.delay(random.randint(1, 100), random.randint(1, 100))
        send_email.delay(f"user{random.randint(1, 100)}@example.com")
        charge_payment.delay(order_id, round(random.uniform(5, 500), 2))
        if random.random() < 0.2:
            generate_report.delay(random.choice([7, 30, 90]))
        order_id += 1
        time.sleep(random.uniform(1.0, 3.0))


if __name__ == "__main__":
    main()
