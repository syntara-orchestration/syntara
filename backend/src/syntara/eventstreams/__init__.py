"""Event-stream consumer worker — NATIVE FastStream implementation (POC).

This is the FastStream counterpart to the ``poc/aiokafka-consumer-worker`` branch.
It implements the *same scope* — a long-running Kafka consumer that sits in front
of Temporal, receives messages, filters them, and hands matching ones off with a
process-then-commit, at-least-once guarantee — but it is written **natively on
FastStream** and deliberately **bypasses the transport-agnostic "AO wrapper"**
(the ``core`` contracts + ``adapters`` factory + ``pipeline``/``registry``) that
the aiokafka branch used.

What that means in practice:

- There is no ``EventConsumer`` interface, no ``build_consumer`` factory, no
  broker-neutral ``DispatchingEventHandler`` pipeline, and no ``EventEnvelope``.
- The broker, the subscription, the ack/nack semantics, the decode->filter->
  dispatch flow, and the message identity are all expressed directly against
  FastStream's Kafka primitives (``KafkaBroker``, ``@broker.subscriber``,
  ``AckPolicy.MANUAL``, ``KafkaMessage``).

This is intentional: it is the "what does the idiomatic native version look like"
artifact for ADR-0001. Because everything is broker-shaped, the cost of a second
transport (EDA / a real Event-Driven Architecture with SQS, Service Bus, Event
Grid, or fan-out to N workflows) lands here as duplication and refactoring. Every
place that would have to be rebuilt is marked with a ``# FUTURE EDA RISK:`` comment
so the trade-off is visible in the code, not just the ADR.

Modules:
- ``static_broker`` — the single hardcoded edit point (broker URL, topics, token)
  and the ``KafkaBroker`` factory (native security mapping lives here).
- ``handlers``     — the Temporal-handoff stub + native ``event_type`` dispatch.
- ``metrics``      — Prometheus counters/histograms (the one genuinely reusable bit).
- ``app``          — the FastStream app: the subscriber callback that folds the whole
  delivery guarantee into one broker-specific function.
- ``consumer_entrypoint`` — ``python -m`` process entry, gated on APP_EVENTSTREAM_ENABLED.
"""

from __future__ import annotations
