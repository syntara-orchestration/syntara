"""Transport-neutral contracts and the delivery-guarantee pipeline.

Nothing in this package imports a broker SDK, so it can be unit-tested with fakes
and reused unchanged across every adapter.
"""

from __future__ import annotations

from syntara.eventstreams.core.connection import (
    BrokerConnection,
    BrokerConnectionProvider,
    BrokerType,
    ConsumerConfig,
    SaslCredentials,
    SaslMechanism,
    SecurityProtocol,
    TlsMaterial,
)
from syntara.eventstreams.core.consumer import EventConsumer
from syntara.eventstreams.core.envelope import EventEnvelope, HandlerResult, Health
from syntara.eventstreams.core.exceptions import (
    ConsumerConnectionError,
    EventStreamError,
    PermanentHandlerError,
    TransientHandlerError,
    UnsupportedBrokerError,
)
from syntara.eventstreams.core.filter import AllowAllFilter, HeaderEqualityFilter, MessageFilter
from syntara.eventstreams.core.handler import EventHandler, WorkflowLauncher
from syntara.eventstreams.core.pipeline import DispatchingEventHandler
from syntara.eventstreams.core.registry import HandlerRegistry, MessageHandlerFn
from syntara.eventstreams.core.serialization import (
    DeserializationError,
    Deserializer,
    JsonDeserializer,
    RawBytesDeserializer,
)

__all__ = [
    "AllowAllFilter",
    "BrokerConnection",
    "BrokerConnectionProvider",
    "BrokerType",
    "ConsumerConfig",
    "ConsumerConnectionError",
    "DeserializationError",
    "Deserializer",
    "DispatchingEventHandler",
    "EventConsumer",
    "EventEnvelope",
    "EventHandler",
    "EventStreamError",
    "HandlerRegistry",
    "HandlerResult",
    "HeaderEqualityFilter",
    "Health",
    "JsonDeserializer",
    "MessageFilter",
    "MessageHandlerFn",
    "PermanentHandlerError",
    "RawBytesDeserializer",
    "SaslCredentials",
    "SaslMechanism",
    "SecurityProtocol",
    "TlsMaterial",
    "TransientHandlerError",
    "UnsupportedBrokerError",
    "WorkflowLauncher",
]
