"""Transport-agnostic event-stream consumer runtime.

A long-running, broker-agnostic pub/sub consumer that sits *in front of* Temporal:
it receives messages from a broker, filters them, and hands matching ones off to
Temporal (which owns durable retries) using a process-then-commit, at-least-once
guarantee (ADR-0001). It is not a Temporal replacement.

Layering:

- ``core`` — transport-neutral contracts and the delivery-guarantee pipeline
  (no broker imports; unit-testable in isolation).
- ``adapters`` — one module per broker; only these import a broker SDK. Kafka
  (aiokafka) is implemented; AWS SNS/SQS/EventBridge and Azure Service Bus/Event
  Grid are on the roadmap as peers behind the same :class:`EventConsumer` contract.
- ``config`` / ``handlers`` / ``consumer_service`` / ``consumer_lifecycle`` /
  ``consumer_entrypoint`` — settings-backed wiring and the process lifecycle.

The broker connection is *injected* (:class:`BrokerConnectionProvider`) so the
UI-configured, per-connector brokers on the roadmap are a drop-in for the POC's
settings-backed provider.
"""

from __future__ import annotations
