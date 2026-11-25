"""Kafka adapter implementing validate() and discover().

validate(): Opens a short-lived Kafka connection and reads broker metadata.
SASL_SSL uses the resolved Kafka credential; SSL and opted-in PLAINTEXT
allow an omitted credential.

discover(): Delegates to validate() and returns an empty DiscoverResult.
Kafka has no discoverable resources at the integration level.
"""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import structlog
from aiokafka.errors import KafkaConnectionError, KafkaError, KafkaTimeoutError

from syntara.core.exceptions import SafeValueError
from syntara.credentials.exceptions import CredentialValidationError
from syntara.credentials.lib.kafka_connection import (
    KafkaSecurityProtocol,
    kafka_credential_required,
    validate_kafka_mtls_configuration,
)
from syntara.credentials.lib.mtls_identity import MTLS_IDENTITY_VARS
from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.kafka_credentials import resolve_kafka_authentication
from syntara.integrations.adapters.kafka_tls import KafkaMTLSError, build_kafka_mtls_context
from syntara.integrations.adapters.protocol import (
    DiscoverResult,
    HealthCheckErrorType,
    ValidateResult,
)
from syntara.integrations.lib.kafka_connection import KafkaHealthClient
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = structlog.stdlib.get_logger(__name__)

_CLIENT_ID = "syntara-kafka-integration"
_MS_PER_SECOND = 1000


class KafkaAuthenticationConfigurationError(ValueError):
    """Kafka connection options require credentials compatible with the security protocol."""


class KafkaAdapter:
    """Adapter for Kafka integrations implementing validate() and discover().

    Connections use SASL_SSL by default. SSL and explicitly opted-in
    PLAINTEXT are also supported. ``allow_http`` is rejected because it would
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
        if not self._config.allow_http and (
            self._config.security_protocol != KafkaSecurityProtocol.PLAINTEXT or self._config.allow_plaintext
        ):
            return None
        return ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="SASL_PLAINTEXT and allow_http are unsupported. PLAINTEXT requires allow_plaintext=true.",
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
        # Accept legacy broker CAs that omit keyUsage while keeping chain and
        # hostname verification enabled.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        if self._config.ca_certificate:
            context.load_verify_locations(cadata=self._config.ca_certificate)
        return context

    def connection_ssl_context(self, resolved_credential: Mapping[str, object]) -> ssl.SSLContext | None:
        """Build the TLS settings for the supplied identity and security protocol."""
        if not MTLS_IDENTITY_VARS.isdisjoint(resolved_credential):
            try:
                validate_kafka_mtls_configuration(
                    security_protocol=self._config.security_protocol,
                    insecure_skip_tls_verify=self._config.insecure_skip_tls_verify,
                )
            except CredentialValidationError as exc:
                raise KafkaAuthenticationConfigurationError(exc.message) from None
            return build_kafka_mtls_context(self._config.ca_certificate, resolved_credential)
        if self._config.security_protocol == KafkaSecurityProtocol.PLAINTEXT:
            return None
        return self._ssl_context()

    def connection_options(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        """Validate credentials and build shared management/runtime options.

        Raises KafkaAuthenticationConfigurationError before constructing TLS or
        network resources when SASL is required and either normalized credential is empty.
        Password whitespace remains part of the stored credential.
        """
        uses_mtls = not MTLS_IDENTITY_VARS.isdisjoint(resolved_credential)
        login = None if uses_mtls else _sasl_login(resolved_credential)
        if not uses_mtls and login is None and kafka_credential_required(self._config.security_protocol):
            msg = "Authentication configuration is incomplete"
            raise KafkaAuthenticationConfigurationError(msg)
        username, password = login or (None, None)
        return {
            "client_id": _CLIENT_ID,
            "security_protocol": self._config.security_protocol,
            "sasl_mechanism": self._config.sasl_mechanism,
            "sasl_plain_username": username,
            "sasl_plain_password": password,
            "ssl_context": self.connection_ssl_context(resolved_credential),
            "request_timeout_ms": timeout_seconds * _MS_PER_SECOND,
        }

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Bootstrap a short-lived client against the configured brokers.

        Args:
            resolved_credential: extra_vars dict from InjectorResolver.resolve().
                Contains SASL login or mutual TLS identity variables.
            timeout_seconds: Maximum seconds for the whole bootstrap. Each broker
                also gets this value as ``request_timeout_ms``, which is only a
                per-attempt budget.

        """
        try:
            options = self.connection_options(resolved_credential, timeout_seconds)
        except KafkaAuthenticationConfigurationError as exc:
            logger.warning("Kafka validate: no usable credentials configured")
            return ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error=str(exc),
                error_type=HealthCheckErrorType.AUTH_FAILURE,
            )
        except KafkaMTLSError as exc:
            logger.warning("Kafka validate TLS setup failed", error_code=exc.code.value)
            return ValidateResult(success=False, checked_at=datetime.now(UTC), error=exc.message, error_type=exc.code)
        rejected = self._plaintext_rejection()
        if rejected is not None:
            logger.warning("Kafka validate rejected an unsafe transport configuration")
            return rejected

        if self._config.security_protocol != KafkaSecurityProtocol.PLAINTEXT and self._config.insecure_skip_tls_verify:
            logger.warning(
                "TLS verification disabled. Connection is vulnerable to MITM attacks",
                bootstrap_servers=self._config.bootstrap_servers,
            )

        return await self._validate_broker_connection(options, timeout_seconds)

    async def _validate_broker_connection(self, options: dict[str, Any], timeout_seconds: int) -> ValidateResult:
        """Probe the brokers and close the health client after each result."""
        client = KafkaHealthClient(
            bootstrap_servers=list(self._config.bootstrap_servers),
            **options,
        )

        success = True
        error_msg: str | None = None
        error_type: HealthCheckErrorType | None = None
        try:
            await _bootstrap(client, timeout_seconds)
            logger.info(
                "Kafka validate succeeded",
                bootstrap_servers=self._config.bootstrap_servers,
                security_protocol=self._config.security_protocol,
            )
        except (TimeoutError, KafkaTimeoutError):
            success = False
            error_msg = f"Connection timed out after {timeout_seconds}s"
            error_type = HealthCheckErrorType.TIMEOUT
            logger.warning("Kafka validate timed out", timeout_seconds=timeout_seconds)
        except KafkaMTLSError as exc:
            success = False
            error_msg = exc.message
            error_type = exc.code
            logger.warning("Kafka validate TLS connection failed", error_code=exc.code.value)
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


async def _bootstrap(client: KafkaHealthClient, timeout_seconds: int) -> None:
    """Bound DNS, socket setup, authentication, and metadata by one deadline.

    Each health client owns its connections. There is no global recorder or
    lock to leak between concurrent calls or consume an unbounded queue wait.
    """
    async with asyncio.timeout(timeout_seconds):
        await client.bootstrap()


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


async def _close_client(client: KafkaHealthClient) -> None:
    try:
        await client.close()
    except Exception:
        logger.exception("Kafka client close failed")


register_health_check_adapter(
    IntegrationType.KAFKA,
    lambda config: KafkaAdapter(cast("KafkaConfiguration", config)),
)
