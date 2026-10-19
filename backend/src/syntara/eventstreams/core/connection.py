"""Resolved Kafka connection parameters for consumer construction.

Carries all arguments needed to build an ``AIOKafkaConsumer`` without
importing credential-resolution or Integration-lookup logic. The
connection provider service (AAP-94561) is responsible for populating
these from a ``SubscriptionSnapshot``; the transport adapter accepts
this type as a ready-to-use input.
"""

from __future__ import annotations

import ssl
from typing import Any, ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class ResolvedKafkaConnection(SQLModel):
    """Immutable, redacted connection parameters for one Kafka consumer."""

    bootstrap_servers: list[str]
    security_protocol: str
    sasl_mechanism: str | None = None
    sasl_plain_username: str | None = None
    sasl_plain_password: str | None = None
    ssl_context: Any | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    def __repr__(self) -> str:
        """Redact secrets from the string representation."""
        return (
            f"ResolvedKafkaConnection(bootstrap_servers={self.bootstrap_servers!r}, "
            f"security_protocol={self.security_protocol!r}, "
            f"sasl_mechanism={self.sasl_mechanism!r}, "
            f"sasl_plain_username={'***' if self.sasl_plain_username else None!r}, "
            f"sasl_plain_password={'***' if self.sasl_plain_password else None!r}, "
            f"ssl_context={'<SSLContext>' if self.ssl_context else None!r})"
        )

    def has_ssl_context(self) -> bool:
        """Return whether an SSL context is present."""
        return isinstance(self.ssl_context, ssl.SSLContext)
