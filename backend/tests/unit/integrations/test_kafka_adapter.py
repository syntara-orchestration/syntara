"""Tests for the Kafka adapter — validate() and discover() methods."""

from __future__ import annotations

import ssl
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiokafka.errors import KafkaConnectionError, KafkaError, KafkaTimeoutError

from syntara.integrations.adapters.kafka import KafkaAdapter
from syntara.integrations.adapters.protocol import HealthCheckErrorType, IntegrationAdapter
from syntara.integrations.models.integration_configuration import KafkaConfiguration

_BROKERS = ["broker.example.com:9093"]
_USERNAME = "kafka-user"
_PASSWORD = "kafka-secret"  # noqa: S105


@pytest.fixture
def kafka_config() -> KafkaConfiguration:
    """Create a test Kafka configuration that uses SASL_SSL."""
    return KafkaConfiguration(bootstrap_servers=_BROKERS)


@pytest.fixture
def resolved_credential() -> dict[str, Any]:
    """Resolved Kafka credential extra_vars."""
    return {
        "auth_type": "kafka_connection",
        "kafka_username": _USERNAME,
        "kafka_password": _PASSWORD,
    }


def _client_mock() -> AsyncMock:
    client = AsyncMock()
    client.bootstrap = AsyncMock()
    client.close = AsyncMock()
    return client


class TestKafkaAdapterProtocol:
    """Tests that KafkaAdapter satisfies the adapter Protocol."""

    def test_is_instance_of_protocol(self, kafka_config: KafkaConfiguration) -> None:
        """Verify KafkaAdapter implements IntegrationAdapter."""
        adapter = KafkaAdapter(kafka_config)
        assert isinstance(adapter, IntegrationAdapter)


class TestKafkaValidateSuccess:
    """Tests for a successful bootstrap."""

    @pytest.mark.asyncio
    async def test_validate_success(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """A completed bootstrap returns success=True and closes the client."""
        client = _client_mock()
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client) as constructor:
            adapter = KafkaAdapter(kafka_config)
            result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is True
        assert result.error is None
        assert result.error_type is None
        assert result.checked_at is not None
        client.bootstrap.assert_awaited_once()
        client.close.assert_awaited_once()
        kwargs = constructor.call_args.kwargs
        assert kwargs["bootstrap_servers"] == _BROKERS
        assert kwargs["security_protocol"] == "SASL_SSL"
        assert kwargs["sasl_mechanism"] == "SCRAM-SHA-256"
        assert kwargs["sasl_plain_username"] == _USERNAME
        assert kwargs["sasl_plain_password"] == _PASSWORD
        assert kwargs["request_timeout_ms"] == 10_000
        assert isinstance(kwargs["ssl_context"], ssl.SSLContext)

    @pytest.mark.asyncio
    async def test_allow_http_rejects_sasl_plaintext(self, resolved_credential: dict[str, Any]) -> None:
        """allow_http would select SASL_PLAINTEXT, which Kafka does not support."""
        config = KafkaConfiguration.model_construct(
            integration_type="kafka",
            bootstrap_servers=_BROKERS,
            sasl_mechanism="SCRAM-SHA-256",
            allow_http=True,
        )
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient") as constructor:
            result = await KafkaAdapter(config).validate(resolved_credential, timeout_seconds=5)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert result.error is not None
        assert "SASL_PLAINTEXT" in result.error
        constructor.assert_not_called()

    @pytest.mark.asyncio
    async def test_plain_mechanism_is_forwarded(self, resolved_credential: dict[str, Any]) -> None:
        """A cluster that uses SASL/PLAIN sends that mechanism to the client."""
        config = KafkaConfiguration(bootstrap_servers=_BROKERS, sasl_mechanism="PLAIN")
        client = _client_mock()
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client) as constructor:
            result = await KafkaAdapter(config).validate(resolved_credential, timeout_seconds=5)

        assert result.success is True
        assert constructor.call_args.kwargs["sasl_mechanism"] == "PLAIN"


class TestKafkaValidateAuth:
    """Tests that missing credentials never open a connection."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "credential",
        [
            {},
            {"kafka_username": "user", "kafka_password": ""},
            {"kafka_username": "  ", "kafka_password": "secret"},
        ],
    )
    async def test_missing_credentials_are_auth_failure(
        self, kafka_config: KafkaConfiguration, credential: dict[str, Any]
    ) -> None:
        """Blank username or password returns AUTH_FAILURE without constructing a client."""
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient") as constructor:
            result = await KafkaAdapter(kafka_config).validate(credential, timeout_seconds=10)

        constructor.assert_not_called()
        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE


class TestKafkaValidateErrors:
    """Tests that client failures become structured results."""

    @pytest.mark.asyncio
    async def test_timeout(self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]) -> None:
        """A broker timeout is reported as TIMEOUT and the client is closed."""
        client = _client_mock()
        client.bootstrap.side_effect = KafkaTimeoutError("timed out")
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client):
            result = await KafkaAdapter(kafka_config).validate(resolved_credential, timeout_seconds=3)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ssl_error(self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]) -> None:
        """An SSL failure is reported as SSL_ERROR."""
        client = _client_mock()
        client.bootstrap.side_effect = ssl.SSLError("certificate verify failed")
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client):
            result = await KafkaAdapter(kafka_config).validate(resolved_credential, timeout_seconds=3)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.SSL_ERROR

    @pytest.mark.asyncio
    async def test_connection_error(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """A broker connection failure is reported as CONNECTION_ERROR."""
        client = _client_mock()
        client.bootstrap.side_effect = KafkaConnectionError("connection refused")
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client):
            result = await KafkaAdapter(kafka_config).validate(resolved_credential, timeout_seconds=3)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_sasl_failure_is_auth(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """A SASL failure is reported as AUTH_FAILURE."""
        client = _client_mock()
        client.bootstrap.side_effect = KafkaError("SaslAuthenticationFailed")
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client):
            result = await KafkaAdapter(kafka_config).validate(resolved_credential, timeout_seconds=3)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert result.error == "Authentication failed"


class TestKafkaDiscover:
    """discover() is a connectivity check with no resources."""

    @pytest.mark.asyncio
    async def test_discover_delegates_to_validate(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """A successful discover returns empty tool and model lists."""
        client = _client_mock()
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client):
            result = await KafkaAdapter(kafka_config).discover(resolved_credential, timeout_seconds=10)

        assert result.success is True
        assert result.discovered_tools is None
        assert result.discovered_models is None


class TestKafkaTlsContext:
    """TLS context follows the shared security mixin."""

    @pytest.mark.asyncio
    async def test_insecure_skip_disables_verification(self, resolved_credential: dict[str, Any]) -> None:
        """insecure_skip_tls_verify builds a context that does not check certificates."""
        config = KafkaConfiguration(bootstrap_servers=_BROKERS, insecure_skip_tls_verify=True)
        client = _client_mock()
        with patch("syntara.integrations.adapters.kafka.AIOKafkaClient", return_value=client) as constructor:
            await KafkaAdapter(config).validate(resolved_credential, timeout_seconds=5)

        context = constructor.call_args.kwargs["ssl_context"]
        assert context.verify_mode == ssl.CERT_NONE
        assert context.check_hostname is False

    def test_custom_ca_is_loaded(self) -> None:
        """A PEM CA is loaded into the default trust store."""
        config = KafkaConfiguration.model_construct(
            integration_type="kafka",
            bootstrap_servers=_BROKERS,
            allow_http=False,
            insecure_skip_tls_verify=False,
            ca_certificate="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
        )
        adapter = KafkaAdapter(config)
        with patch.object(ssl.SSLContext, "load_verify_locations") as load_ca:
            context = adapter._ssl_context()
        assert isinstance(context, ssl.SSLContext)
        load_ca.assert_called_once()
