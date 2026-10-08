"""TEMPORARY hardcoded broker connection — the single place to edit for now.

Stand-in for the eventual ``IntegrationBrokerConnectionProvider`` that will read
the broker URL + topics from a user-created **Integration** and the auth token from
its linked **Credential** (ADR-0001; ANSTRAT-1934). Until that domain wiring
exists, every connection value is hardcoded here — deliberately NOT in
settings/config — so there is exactly one place to change while iterating against a
broker deployed elsewhere.

    # TODO(ANSTRAT-1934): replace the constants below + build_broker() with a
    #   provider that reads broker URL + security from Integration.configuration and
    #   the token from the linked Credential (SecretService).

Unlike the aiokafka branch, there is no transport-neutral ``BrokerConnection``
value object here: this module builds a **FastStream ``KafkaBroker`` directly**, so
the security mapping is Kafka-shaped.
"""

from __future__ import annotations

import ssl

from faststream.kafka import KafkaBroker
from faststream.security import BaseSecurity, SASLPlaintext, SASLScram256, SASLScram512

# --------------------------------------------------------------------------- #
# EDIT THESE — the broker deployed elsewhere. (Future: from Integration.)     #
# --------------------------------------------------------------------------- #
BOOTSTRAP_SERVERS = "CHANGE_ME:9092"  # e.g. "pkc-xxxxx.us-east-1.aws.confluent.cloud:9092"
TOPICS: tuple[str, ...] = ("syntara-events",)
GROUP_ID = "syntara-eventstream"
AUTO_OFFSET_RESET = "earliest"  # "earliest" | "latest"

# Transport security + auth. (Future: security from Integration, token from Credential.)
# "PLAINTEXT" | "SSL" | "SASL_SSL" | "SASL_PLAINTEXT"
SECURITY_PROTOCOL = "SASL_SSL"
# "PLAIN" | "SCRAM-SHA-256" | "SCRAM-SHA-512"
SASL_MECHANISM = "PLAIN"
SASL_USERNAME = "CHANGE_ME"  # API key / principal

# EDIT THIS — the secret token. (Future: decrypted from the linked Credential.)
SASL_TOKEN = "CHANGE_ME"  # noqa: S105 — placeholder; real value comes from a Credential

# Consumer tuning (process-level, kept alongside the connection for a single source).
HANDLER_TIMEOUT_SECONDS = 300.0
RETRY_BACKOFF_SECONDS = 2.0


def _build_security() -> BaseSecurity | None:
    """Map the hardcoded protocol/mechanism onto a FastStream security object.

    # FUTURE EDA RISK: this security mapping is Kafka/FastStream-typed. In the AO
    # wrapper it lived behind a broker-neutral ``SecurityProtocol``/``SaslCredentials``
    # value object that every adapter shared. Here the return type is FastStream's
    # ``BaseSecurity`` hierarchy (``SASLPlaintext``/``SASLScram*``), so a second
    # transport (SQS IAM, Service Bus SAS, Event Grid keys) cannot reuse ANY of
    # this — it needs its own auth construction. When EDA lands, either this whole
    # function is duplicated per broker or a broker-neutral security abstraction has
    # to be reintroduced (i.e. rebuild the layer this POC deleted).
    #
    # FUTURE EDA RISK: GSSAPI / OAUTHBEARER are not expressible via FastStream's
    # security classes here, so those mechanisms are unsupported by construction.
    """
    use_ssl = SECURITY_PROTOCOL in ("SSL", "SASL_SSL")

    # Managed broker: default system trust store (publicly-trusted server cert).
    ssl_context = ssl.create_default_context() if use_ssl else None

    if SECURITY_PROTOCOL in ("PLAINTEXT", "SSL"):
        # No SASL — TLS only (or nothing).
        return BaseSecurity(ssl_context=ssl_context, use_ssl=use_ssl) if use_ssl else None

    # SASL_SSL / SASL_PLAINTEXT — pick the class by mechanism.
    if SASL_MECHANISM == "PLAIN":
        return SASLPlaintext(username=SASL_USERNAME, password=SASL_TOKEN, use_ssl=use_ssl)
    if SASL_MECHANISM == "SCRAM-SHA-256":
        return SASLScram256(username=SASL_USERNAME, password=SASL_TOKEN, use_ssl=use_ssl)
    if SASL_MECHANISM == "SCRAM-SHA-512":
        return SASLScram512(username=SASL_USERNAME, password=SASL_TOKEN, use_ssl=use_ssl)

    msg = f"unsupported SASL mechanism for the FastStream POC: {SASL_MECHANISM!r}"
    raise ValueError(msg)


def build_broker() -> KafkaBroker:
    """Construct the FastStream ``KafkaBroker`` for the hardcoded connection.

    # FUTURE EDA RISK: the return type is a concrete ``KafkaBroker``. In the AO
    # wrapper the equivalent was a broker-neutral ``BrokerConnection`` consumed by a
    # ``build_consumer`` factory that could return a Kafka/SQS/ServiceBus consumer
    # behind one ``EventConsumer`` interface. Native FastStream has no such seam:
    # ``KafkaBroker`` is not swappable for an ``SQSBroker``/``ServiceBusBroker``
    # without touching every call site that types against it (app.py below). Adding
    # a transport means either a parallel ``build_*_broker`` + parallel app, or
    # reintroducing the factory the POC removed.
    """
    return KafkaBroker(
        BOOTSTRAP_SERVERS,
        security=_build_security(),
        # One in-flight message at a time so the manual offset commit is always
        # correct (process-then-commit). Kafka-native parallelism = more partitions
        # + more consumer-group replicas.
        graceful_timeout=HANDLER_TIMEOUT_SECONDS,
    )
