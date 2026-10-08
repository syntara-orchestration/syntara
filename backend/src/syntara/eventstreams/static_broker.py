"""TEMPORARY hardcoded broker connection — the single place to edit for now.

This is a stand-in for the eventual ``IntegrationBrokerConnectionProvider`` that
will read the broker URL + topics from a user-created **Integration** and the
auth token from its linked **Credential** (ADR-0001; ANSTRAT-1934). Until that
domain wiring exists, every connection value is hardcoded here — deliberately NOT
in settings/config — so there is exactly one place to change while iterating
against a broker that is deployed elsewhere.

It implements the :class:`BrokerConnectionProvider` protocol structurally, so
swapping it for the real DB-backed provider later is a one-line change at the
``start_consumer`` call site — nothing else in the runtime changes.

    # TODO(ANSTRAT-1934): replace with IntegrationBrokerConnectionProvider
    #   get_connection()      -> broker URL + security from Integration.configuration
    #   get_consumer_config() -> topics + group from Integration.configuration
    #   sasl.password         -> token from the linked Credential (SecretService)
"""

from __future__ import annotations

from pydantic import SecretStr

from syntara.eventstreams.core.connection import (
    BrokerConnection,
    BrokerType,
    ConsumerConfig,
    SaslCredentials,
    SaslMechanism,
    SecurityProtocol,
)

# --------------------------------------------------------------------------- #
# EDIT THESE — the broker deployed elsewhere. (Future: from Integration.)     #
# --------------------------------------------------------------------------- #
BOOTSTRAP_SERVERS = "CHANGE_ME:9092"  # e.g. "pkc-xxxxx.us-east-1.aws.confluent.cloud:9092"
TOPICS: tuple[str, ...] = ("syntara-events",)
GROUP_ID = "syntara-eventstream"
AUTO_OFFSET_RESET = "earliest"  # "earliest" | "latest"

# Transport security + auth. (Future: security from Integration, token from Credential.)
SECURITY_PROTOCOL = SecurityProtocol.SASL_SSL
SASL_MECHANISM = SaslMechanism.PLAIN
SASL_USERNAME = "CHANGE_ME"  # API key / principal (None if not needed)

# EDIT THIS — the secret token. (Future: decrypted from the linked Credential.)
SASL_TOKEN = "CHANGE_ME"  # noqa: S105 — placeholder; real value comes from a Credential

# Consumer tuning (process-level, kept alongside the connection for a single source).
HANDLER_TIMEOUT_SECONDS = 300.0
RETRY_BACKOFF_SECONDS = 2.0
MAX_CONCURRENT_HANDLERS = 1


class StaticBrokerConnectionProvider:
    """Returns a hardcoded :class:`BrokerConnection` + :class:`ConsumerConfig`.

    Temporary stand-in for the Integration/Credential-backed provider. Implements
    the :class:`BrokerConnectionProvider` protocol structurally.
    """

    async def get_connection(self) -> BrokerConnection:
        """Return the hardcoded broker connection (URL + security + token)."""
        return BrokerConnection(
            broker_type=BrokerType.KAFKA,
            bootstrap_servers=BOOTSTRAP_SERVERS,
            security_protocol=SECURITY_PROTOCOL,
            tls=None,  # managed broker: default system trust store (see kafka adapter)
            sasl=SaslCredentials(
                mechanism=SASL_MECHANISM,
                username=SASL_USERNAME,
                password=SecretStr(SASL_TOKEN),
            ),
        )

    async def get_consumer_config(self) -> ConsumerConfig:
        """Return the hardcoded topics + consumer tuning."""
        return ConsumerConfig(
            topics=TOPICS,
            group_id=GROUP_ID,
            auto_offset_reset=AUTO_OFFSET_RESET,
            max_concurrent_handlers=MAX_CONCURRENT_HANDLERS,
            handler_timeout_seconds=HANDLER_TIMEOUT_SECONDS,
            retry_backoff_seconds=RETRY_BACKOFF_SECONDS,
        )
