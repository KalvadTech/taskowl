"""Tests for the test data generator's transport-aware logic."""

import importlib.util
from pathlib import Path

from kombu import Exchange

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_test_data.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_test_data", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_exchange_amqp_uses_topic():
    """AMQP transports should use a topic exchange."""
    module = _load_module()
    exchange = module._build_exchange("amqp://guest:guest@localhost:5672//")
    assert isinstance(exchange, Exchange)
    assert exchange.name == "celeryev"
    assert exchange.type == "topic"


def test_build_exchange_amqps_uses_topic():
    """amqps transports should use a topic exchange."""
    module = _load_module()
    exchange = module._build_exchange("amqps://user:pass@host/")
    assert exchange.type == "topic"


def test_build_exchange_redis_uses_fanout():
    """Redis transports should use a fanout exchange (pub/sub)."""
    module = _load_module()
    exchange = module._build_exchange("redis://localhost:6379/0")
    assert exchange.name == "celeryev"
    assert exchange.type == "fanout"


def test_publish_routing_key_derived_from_type():
    """Routing key should be the event type with '-' replaced by '.'."""
    _load_module()
    events = [
        ("task-received", "task.received"),
        ("task-started", "task.started"),
        ("worker-heartbeat", "worker.heartbeat"),
        ("worker-online", "worker.online"),
    ]
    for event_type, expected_key in events:
        routing_key = event_type.replace("-", ".")
        assert routing_key == expected_key
