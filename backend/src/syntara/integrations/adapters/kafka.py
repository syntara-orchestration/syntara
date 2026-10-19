"""Kafka adapter implementing validate() and discover().

validate(): Opens a short-lived SASL client and bootstraps against the
configured brokers. Username and password come from the resolved
Kafka credential.

discover(): Delegates to validate() and returns an empty DiscoverResult.
Kafka has no discoverable resources at the integration level.
"""

from __future__ import annotations

import ssl
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from aiokafka.client import AIOKafkaClient
from aiokafka.errors import KafkaConnectionError, KafkaError, KafkaTimeoutError

from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.protocol import (
    DiscoverResult,
    HealthCheckErrorType,
    ValidateResult,
)
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration  # noqa: TC001

logger = structlog.stdlib.get_logger(__name__)

_KAFKA_USERNAME_KEY = "kafka_username"
_KAFKA_PASSWORD_KEY = "kafka_password"  # noqa: S105
_CLIENT_ID = "syntara-kafka-integration"
_MS_PER_SECOND = 1000


class KafkaAdapter:
    """Adapter for Kafka integrations implementing validate() and discover().

    Connections use SASL_SSL. ``allow_http`` is rejected because it would
    select SASL_PLAINTEXT. ``sasl_mechanism`` selects PLAIN, SCRAM-SHA-256,
    or SCRAM-SHA-512. The default is SCRAM-SHA-256.
    ``insecure_skip_tls_verify`` and ``ca_certificate`` keep the shared
    security-mixin meaning. discover() delegates to validate() because a
    cluster has no tools or models to sync.
    """

    def __init__(self, config: KafkaConfiguration) -> None:
        """Initialize with Kafka configuration.

        Args:
            config: Non-sensitive integration configuration containing
                bootstrap servers and TLS settings.

        """
        self._config = config

    def _plaintext_rejection(self) -> ValidateResult | None:
        if not self._config.allow_http:
            return None
        return ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Kafka does not support SASL_PLAINTEXT. Use SASL_SSL.",
            error_type=HealthCheckErrorType.CONNECTION_ERROR,
        )

    def _ssl_context(self) -> ssl.SSLContext:
        if self._config.insecure_skip_tls_verify:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        context = ssl.create_default_context()
        if self._config.ca_certificate:
            context.load_verify_locations(cadata=self._config.ca_certificate)
        return context

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Bootstrap a SASL client against the configured brokers.

        Args:
            resolved_credential: extra_vars dict from InjectorResolver.resolve().
                Recognized keys: ``kafka_username``, ``kafka_password``.
            timeout_seconds: Maximum seconds to wait for the bootstrap.

        """
        username = str(resolved_credential.get(_KAFKA_USERNAME_KEY) or "").strip()
        password = str(resolved_credential.get(_KAFKA_PASSWORD_KEY) or "").strip()
        if not username or not password:
            logger.warning("Kafka validate: no usable credentials configured")
            return ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Authentication configuration is incomplete",
                error_type=HealthCheckErrorType.AUTH_FAILURE,
            )
        rejected = self._plaintext_rejection()
        if rejected is not None:
            logger.warning("Kafka validate rejected SASL_PLAINTEXT")
            return rejected

        if self._config.insecure_skip_tls_verify:
            logger.warning(
                "TLS verification disabled. Connection is vulnerable to MITM attacks",
                bootstrap_servers=self._config.bootstrap_servers,
            )

        client = AIOKafkaClient(
            bootstrap_servers=list(self._config.bootstrap_servers),
            client_id=_CLIENT_ID,
            security_protocol="SASL_SSL",
            sasl_mechanism=self._config.sasl_mechanism,
            sasl_plain_username=username,
            sasl_plain_password=password,
            ssl_context=self._ssl_context(),
            request_timeout_ms=timeout_seconds * _MS_PER_SECOND,
        )

        success = True
        error_msg: str | None = None
        error_type: HealthCheckErrorType | None = None
        try:
            await client.bootstrap()
            logger.info(
                "Kafka validate succeeded",
                bootstrap_servers=self._config.bootstrap_servers,
                security_protocol="SASL_SSL",
            )
        except (TimeoutError, KafkaTimeoutError):
            success = False
            error_msg = f"Connection timed out after {timeout_seconds}s"
            error_type = HealthCheckErrorType.TIMEOUT
            logger.warning("Kafka validate timed out", timeout_seconds=timeout_seconds)
        except ssl.SSLError as exc:
            success = False
            error_msg = "SSL/TLS verification failed"
            error_type = HealthCheckErrorType.SSL_ERROR
            logger.warning("Kafka validate SSL error", error=str(exc))
        except KafkaConnectionError as exc:
            success = False
            error_type, error_msg = _classify_kafka_error(exc)
            logger.warning("Kafka validate connection error", error_type=error_type.value, error=str(exc))
        except KafkaError as exc:
            success = False
            error_type, error_msg = _classify_kafka_error(exc)
            logger.warning("Kafka validate protocol error", error_type=error_type.value, error=str(exc))
        except Exception as exc:
            success = False
            error_msg = "Request failed unexpectedly"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.exception("Unexpected error during Kafka validate", error=str(exc))
        finally:
            await _close_client(client)

        return ValidateResult(
            success=success,
            checked_at=datetime.now(UTC),
            error=error_msg,
            error_type=error_type,
        )

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        """Confirm the cluster is reachable.

        Kafka has no discoverable resources at the integration level.
        This method delegates to validate() and returns an empty DiscoverResult.

        Args:
            resolved_credential: extra_vars dict from InjectorResolver.resolve().
            timeout_seconds: Maximum seconds to wait for the bootstrap.

        """
        result = await self.validate(resolved_credential, timeout_seconds)
        return DiscoverResult(
            success=result.success,
            checked_at=result.checked_at,
            error=result.error,
            error_type=result.error_type,
            discovered_tools=None,
            discovered_models=None,
        )


def _classify_kafka_error(exc: KafkaError) -> tuple[HealthCheckErrorType, str]:
    message = str(exc).lower()
    if "auth" in message or "sasl" in message:
        return HealthCheckErrorType.AUTH_FAILURE, "Authentication failed"
    return HealthCheckErrorType.CONNECTION_ERROR, "Unable to connect to Kafka"


async def _close_client(client: AIOKafkaClient) -> None:
    try:
        await client.close()
    except Exception:
        logger.exception("Kafka client close failed")


register_health_check_adapter(
    IntegrationType.KAFKA,
    lambda config: KafkaAdapter(cast("KafkaConfiguration", config)),
)
