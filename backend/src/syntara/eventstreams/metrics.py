"""Prometheus metrics for the FastStream consumer.

Registered against the default registry so ``prometheus_client.start_http_server``
in the entrypoint exposes them on ``metrics_worker_port`` — the same scrape path the
Temporal workers use. With no DLQ to inspect after the fact, the redelivery rate is
the primary production signal (ADR-0001).

These metric definitions are the one part of the aiokafka POC that is genuinely
transport-neutral and could be reused verbatim. Note, though, the ``broker_type``
label is now always ``"kafka"`` at the call site (there is no broker abstraction to
vary it), and ``ASSIGNED_PARTITIONS`` is a Kafka-only concept.
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

# FUTURE EDA RISK: "assigned partitions" is a Kafka-specific health signal. A second
# transport (SQS/Service Bus) has no partition assignment, so this gauge does not
# generalize — the broker-neutral ``health()`` snapshot the AO wrapper exposed would
# have to be reinvented to give every transport a comparable liveness metric.
ASSIGNED_PARTITIONS = Gauge(
    f"{_NS}_assigned_partitions",
    "Partitions currently assigned to this consumer instance.",
    ["broker_type", "group_id"],
)
