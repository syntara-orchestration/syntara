"""Per-broker router modules — one file per transport, by necessity.

That there is one module per transport (rather than one parametrised module) is not a
style choice: FastStream routers are type-coupled to their broker family (verified —
``RedisBroker.include_router(KafkaRouter)`` raises ``SetupError``), so each transport
needs its own broker, its own Router, and its own ``@subscriber`` definitions.
"""

from __future__ import annotations

from syntara.eventstreams.multicloud.brokers.aws_router import BrokerNotAvailableError

__all__ = ["BrokerNotAvailableError"]
