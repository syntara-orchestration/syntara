"""Transport-neutral broker connection descriptors.

These value objects carry everything an adapter needs to connect. Critically,
they are *injected* — for now they are built by the temporary hardcoded
:class:`syntara.eventstreams.static_broker.StaticBrokerConnectionProvider`, but the
same objects will be built from a user-created Kafka connector (an Integration + a
Credential) at runtime. Nothing in ``core`` or the adapters reads settings
directly, so a dynamic, per-connector, multi-tenant provider is a drop-in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import SecretStr


class BrokerType(str, Enum):
    """Supported / planned broker families. Only ``KAFKA`` has an adapter today."""

    KAFKA = "kafka"


class SecurityProtocol(str, Enum):
    """Transport security, named to match Kafka but reusable across brokers."""

    PLAINTEXT = "PLAINTEXT"
    SSL = "SSL"
    SASL_PLAINTEXT = "SASL_PLAINTEXT"
    SASL_SSL = "SASL_SSL"


class SaslMechanism(str, Enum):
    """SASL mechanisms supported for authentication."""

    PLAIN = "PLAIN"
    SCRAM_SHA_256 = "SCRAM-SHA-256"
    SCRAM_SHA_512 = "SCRAM-SHA-512"
    GSSAPI = "GSSAPI"
    OAUTHBEARER = "OAUTHBEARER"


@dataclass(frozen=True, slots=True)
class TlsMaterial:
    """Paths to PEM material for a TLS/mTLS connection to a broker.

    When only ``ca_cert_path`` is set the connection verifies the server; add
    ``cert_path`` + ``key_path`` for mutual TLS.
    """

    ca_cert_path: str | None = None
    cert_path: str | None = None
    key_path: str | None = None


@dataclass(frozen=True, slots=True)
class SaslCredentials:
    """SASL username/password. ``password`` is masked in logs via ``SecretStr``."""

    mechanism: SaslMechanism
    username: str | None = None
    password: SecretStr | None = None


@dataclass(frozen=True, slots=True)
class BrokerConnection:
    """Everything needed to connect to one broker, transport-neutral.

    ``bootstrap_servers`` is the Kafka term; other adapters reuse it as the
    endpoint/namespace. ``extra`` carries vendor-specific keys (e.g. an AWS
    region or an Azure entity path) without widening the shared shape.
    """

    broker_type: BrokerType
    bootstrap_servers: str
    security_protocol: SecurityProtocol = SecurityProtocol.PLAINTEXT
    tls: TlsMaterial | None = None
    sasl: SaslCredentials | None = None
    extra: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConsumerConfig:
    """Per-subscription consumer tuning, independent of the connection."""

    topics: tuple[str, ...]
    group_id: str
    auto_offset_reset: str = "earliest"
    max_concurrent_handlers: int = 1
    handler_timeout_seconds: float = 300.0
    retry_backoff_seconds: float = 2.0


@runtime_checkable
class BrokerConnectionProvider(Protocol):
    """Resolves the connection + consumer config for a subscription.

    The POC ships a settings-backed provider. A future implementation will read
    a Kafka connector row from the Integrations domain and its linked Credential,
    supporting many brokers configured by users in the UI — without touching any
    adapter or the runtime.
    """

    async def get_connection(self) -> BrokerConnection:
        """Return the broker connection descriptor for this subscription."""
        ...

    async def get_consumer_config(self) -> ConsumerConfig:
        """Return the consumer tuning for this subscription."""
        ...
