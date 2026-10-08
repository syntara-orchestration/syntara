"""Prometheus metrics for the consumer runtime.

Registered against the default registry so ``prometheus_client.start_http_server``
in the consumer lifecycle exposes them on ``metrics_worker_port`` — the same
scrape path both Temporal workers use. With no DLQ to inspect after the fact, the
redelivery rate and consumer lag are the primary production signals (ADR-0001).
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

_NS = "orchestrator_eventstream"

MESSAGES_RECEIVED = Counter(
    f"{_NS}_messages_received_total",
    "Messages received from a broker.",
    ["broker_type", "source"],
)

MESSAGES_HANDLED = Counter(
    f"{_NS}_messages_handled_total",
    "Messages after handling, labelled by outcome (ack_triggered/ack_no_trigger/retry/error).",
    ["broker_type", "source", "outcome"],
)

HANDOFF_LATENCY = Histogram(
    f"{_NS}_handoff_latency_seconds",
    "Time from receiving a message to completing the workflow handoff.",
    ["broker_type", "source"],
)

REDELIVERIES = Counter(
    f"{_NS}_redeliveries_total",
    "Messages withheld from commit (RETRY) and redelivered — key back-pressure signal.",
    ["broker_type", "source"],
)

ASSIGNED_PARTITIONS = Gauge(
    f"{_NS}_assigned_partitions",
    "Partitions currently assigned to this consumer instance.",
    ["broker_type", "group_id"],
)
