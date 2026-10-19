"""Kafka adapter implementing validate() and discover().

validate(): Opens a short-lived SASL client and bootstraps against the
configured brokers. Username and password come from the resolved
Kafka credential.

discover(): Delegates to validate() and returns an empty DiscoverResult.
Kafka has no discoverable resources at the integration level.
"""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, cast

import structlog
from aiokafka import client as aiokafka_client
from aiokafka.client import AIOKafkaClient
from aiokafka.errors import KafkaConnectionError, KafkaError, KafkaTimeoutError

from syntara.core.exceptions import SafeValueError
from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.kafka_credentials import resolve_kafka_authentication
from syntara.integrations.adapters.protocol import (
    DiscoverResult,
    HealthCheckErrorType,
    ValidateResult,
)
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.stdlib.get_logger(__name__)

_CLIENT_ID = "syntara-kafka-integration"
_MS_PER_SECOND = 1000
# bootstrap() calls the module-level create_conn. Serializing the recorder swap
# keeps concurrent validates from restoring the wrong function.
_BOOTSTRAP_LOCK = asyncio.Lock()


class _KafkaClientModule(Protocol):
    """Type the internal connection hook aiokafka neither exports nor annotates."""

    create_conn: Callable[..., Awaitable[object]]


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
            # Explicit, documented opt-in (see class docstring and
            # IntegrationSecurityMixin). Same reviewed pattern already used
            # for Postgres connections in core/database/ssl.py; validate()
            # logs a warning so the MITM exposure is visible to operators.
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # NOSONAR
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE  # NOSONAR
            return context
        context = ssl.create_default_context()  # NOSONAR
        if self._config.ca_certificate:
            context.load_verify_locations(cadata=self._config.ca_certificate)
        return context

    def connection_options(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        """Build shared connection/TLS options for management and runtime tests."""
        username, password = resolve_kafka_authentication(resolved_credential)
        return {
            "client_id": _CLIENT_ID,
            "security_protocol": "SASL_SSL",
            "sasl_mechanism": self._config.sasl_mechanism,
            "sasl_plain_username": username,
            "sasl_plain_password": password,
            "ssl_context": self._ssl_context(),
            "request_timeout_ms": timeout_seconds * _MS_PER_SECOND,
        }

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Bootstrap a SASL client against the configured brokers.

        Args:
            resolved_credential: extra_vars dict from InjectorResolver.resolve().
                Recognized keys: ``kafka_username``, ``kafka_password``.
            timeout_seconds: Maximum seconds for the whole bootstrap. Each broker
                also gets this value as ``request_timeout_ms``, which is only a
                per-attempt budget.

        """
        login = _sasl_login(resolved_credential)
        if login is None:
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
            **self.connection_options(resolved_credential, timeout_seconds),
        )

        success = True
        error_msg: str | None = None
        error_type: HealthCheckErrorType | None = None
        try:
            await _bootstrap(client, timeout_seconds)
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
        except OSError as exc:
            success = False
            error_msg = "Unable to connect to Kafka"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.warning("Kafka validate connection error", error_type=error_type.value, error=str(exc))
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


async def _bootstrap(client: AIOKafkaClient, timeout_seconds: int) -> None:
    """Bootstrap every broker under one deadline and keep the original failure.

    ``request_timeout_ms`` is a fresh budget for each broker. ``bootstrap`` then
    catches that attempt's error and, once every broker has failed, raises a
    generic ``KafkaConnectionError`` with no cause. Record the connection-layer
    exception and raise it instead, so a bad password, a certificate failure,
    and a timeout stay distinguishable. ``asyncio.timeout`` cancels the whole
    loop when the caller's deadline expires.
    """
    captured: list[BaseException] = []
    client_module = cast("_KafkaClientModule", aiokafka_client)
    original_create_conn = client_module.create_conn

    async def _recording_create_conn(*args: object, **kwargs: object) -> object:
        try:
            return await original_create_conn(*args, **kwargs)
        except Exception as exc:
            captured.append(exc)
            raise

    async with _BOOTSTRAP_LOCK:
        client_module.create_conn = _recording_create_conn
        try:
            async with asyncio.timeout(timeout_seconds):
                await client.bootstrap()
        except KafkaConnectionError:
            if captured:
                raise captured[-1] from None
            raise
        finally:
            client_module.create_conn = original_create_conn


def _sasl_login(resolved_credential: dict[str, Any]) -> tuple[str, str] | None:
    """Return the SASL username and the stored password.

    ``strip()`` is only the blank check for the password. The value sent to
    the broker keeps any leading or trailing whitespace.
    """
    try:
        return resolve_kafka_authentication(resolved_credential)
    except SafeValueError:
        return None


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
