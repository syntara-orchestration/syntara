"""Multi-cloud EDA extension of the native FastStream consumer (Kafka + AWS + Azure).

This package extends the native FastStream POC to consume messages of UNKNOWN shape
(no fixed schema — payloads differ per workflow and per customer) from three
transports — Kafka, AWS (SQS/SNS), and Azure Service Bus. Each broker handler does the
same three things: decode the raw bytes, filter in the listener node, and hand the
WHOLE decoded message off to Temporal (fan-out). It uses the first-party FastStream
features that still apply once there is no schema: typed ``Router``s, ``Depends``
dependency injection, a ``BaseMiddleware`` for observability, and ``TestBroker`` for
tests. Note what is NOT used: Pydantic parse-from-annotation — with no schema there is
nothing to parse into, so FastStream's headline consume-side feature contributes
nothing here (see ``pipeline.py``).

It is also an honest experiment. Three facts were verified against the installed
FastStream (0.7.7) before writing a line of this package:

1. FastStream ships **no first-party AWS (SQS/SNS) or Azure (Service Bus) broker**.
   The only broker families that exist are: kafka, confluent, rabbit, nats, redis,
   mqtt. AWS/Azure support would require a third-party package or a broker we author
   ourselves. See ``brokers/aws_router.py`` / ``brokers/azure_router.py``.
2. ``FastStream(*brokers)`` DOES accept multiple brokers in one app.
3. Routers are **type-coupled**: ``RedisBroker.include_router(KafkaRouter)`` raises
   ``SetupError: Router must be an instance of RedisRegistrator``. So a subscriber,
   router, or decorator written for one family cannot be mounted on another — every
   subscription must be re-authored per transport.

Where abstraction HOLDS (shared, transport-neutral, written once):
- ``pipeline``     — decode -> filter -> hand off (the whole listener core).
- ``dependencies`` — the ``Depends`` provider callables themselves.

Where FastStream FORCES duplication (marked ``# DUPLICACY RISK [BROKER-SPECIFIC]``):
- ``brokers/*``    — one broker + one typed Router + one ``@subscriber`` + one ack
  path + one connection/security block, PER transport.
- ``middleware``   — registration per broker.
- ``app``          — per-broker lifecycle composition.
"""

from __future__ import annotations
