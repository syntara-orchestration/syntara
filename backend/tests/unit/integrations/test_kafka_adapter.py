"""Tests for the Kafka adapter — validate() and discover() methods."""

from __future__ import annotations

import asyncio
import ssl
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiokafka import client as aiokafka_client
from aiokafka.errors import AuthenticationFailedError, KafkaConnectionError, KafkaError, KafkaTimeoutError

from syntara.integrations.adapters.kafka import KafkaAdapter, KafkaAuthenticationConfigurationError
from syntara.integrations.adapters.protocol import HealthCheckErrorType, IntegrationAdapter
from syntara.integrations.lib.kafka_connection import KafkaHealthClient
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
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client) as constructor:
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
    async def test_password_whitespace_is_preserved(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """Leading and trailing spaces are part of the SASL password."""
        client = _client_mock()
        password_with_spaces = f"  {_PASSWORD}  "
        credential = {**resolved_credential, "kafka_password": password_with_spaces}
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client) as constructor:
            result = await KafkaAdapter(kafka_config).validate(credential, timeout_seconds=10)

        assert result.success is True
        assert constructor.call_args.kwargs["sasl_plain_password"] == password_with_spaces

    @pytest.mark.asyncio
    async def test_allow_http_rejects_sasl_plaintext(self, resolved_credential: dict[str, Any]) -> None:
        """allow_http would select SASL_PLAINTEXT, which Kafka does not support."""
        config = KafkaConfiguration.model_construct(
            integration_type="kafka",
            bootstrap_servers=_BROKERS,
            sasl_mechanism="SCRAM-SHA-256",
            allow_http=True,
        )
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient") as constructor:
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
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client) as constructor:
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
            {"kafka_username": "user", "kafka_password": "   "},
            {"kafka_username": "  ", "kafka_password": "secret"},
            {"kafka_username": "user", "kafka_password": " \t"},
            {"kafka_username": None, "kafka_password": "secret"},
        ],
    )
    async def test_missing_credentials_are_auth_failure(
        self, kafka_config: KafkaConfiguration, credential: dict[str, Any]
    ) -> None:
        """Blank username or password returns AUTH_FAILURE without constructing a client."""
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient") as constructor:
            result = await KafkaAdapter(kafka_config).validate(credential, timeout_seconds=10)

        constructor.assert_not_called()
        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    def test_connection_options_reject_blank_credentials_before_tls_setup(
        self, kafka_config: KafkaConfiguration
    ) -> None:
        """Direct helper callers receive the same validation before resource setup."""
        adapter = KafkaAdapter(kafka_config)
        with patch.object(adapter, "_ssl_context") as tls:
            with pytest.raises(
                KafkaAuthenticationConfigurationError, match="Authentication configuration is incomplete"
            ):
                adapter.connection_options({"kafka_username": "user", "kafka_password": " \t"}, 10)
        tls.assert_not_called()


class TestKafkaValidateErrors:
    """Tests that client failures become structured results."""

    @pytest.mark.asyncio
    async def test_timeout(self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]) -> None:
        """A broker timeout is reported as TIMEOUT and the client is closed."""
        client = _client_mock()
        client.bootstrap.side_effect = KafkaTimeoutError("timed out")
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client):
            result = await KafkaAdapter(kafka_config).validate(resolved_credential, timeout_seconds=3)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ssl_error(self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]) -> None:
        """An SSL failure is reported as SSL_ERROR."""
        client = _client_mock()
        client.bootstrap.side_effect = ssl.SSLError("certificate verify failed")
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client):
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
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client):
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
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client):
            result = await KafkaAdapter(kafka_config).validate(resolved_credential, timeout_seconds=3)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert result.error == "Authentication failed"


class TestKafkaRealBootstrap:
    """bootstrap() itself, with the failure injected at the connection layer.

    Keep the real broker-attempt loop so connection errors and the overall
    deadline are exercised below the adapter mock boundary.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("failure", "error_type", "error"),
        [
            (
                AuthenticationFailedError("password rejected"),
                HealthCheckErrorType.AUTH_FAILURE,
                "Authentication failed",
            ),
            (ssl.SSLError("certificate verify failed"), HealthCheckErrorType.SSL_ERROR, "SSL/TLS verification failed"),
            (TimeoutError(), HealthCheckErrorType.TIMEOUT, "Connection timed out after 1s"),
            (OSError("connection refused"), HealthCheckErrorType.CONNECTION_ERROR, "Unable to connect to Kafka"),
        ],
    )
    async def test_connection_layer_failure_keeps_its_classification(
        self,
        resolved_credential: dict[str, Any],
        failure: BaseException,
        error_type: HealthCheckErrorType,
        error: str,
    ) -> None:
        """A real bootstrap reports the connection error, not a generic connect failure."""
        attempts = 0

        async def fail_create_conn(*_args: object, **_kwargs: object) -> None:
            nonlocal attempts
            attempts += 1
            raise failure

        config = KafkaConfiguration(bootstrap_servers=["broker-a.example:9093", "broker-b.example:9093"])
        with patch("syntara.integrations.lib.kafka_connection._PinnedKafkaConnection.connect", fail_create_conn):
            result = await KafkaAdapter(config).validate(resolved_credential, timeout_seconds=1)

        assert attempts == 2
        assert result.success is False
        assert result.error_type == error_type
        assert result.error == error

    @pytest.mark.asyncio
    async def test_deadline_cancels_before_the_second_broker(self, resolved_credential: dict[str, Any]) -> None:
        """One deadline covers every broker, and cancelling the attempt closes the client."""
        attempts = 0
        attempt_finished = False
        closed: list[KafkaHealthClient] = []
        real_close = KafkaHealthClient.close

        async def hang_create_conn(*_args: object, **_kwargs: object) -> None:
            nonlocal attempts, attempt_finished
            attempts += 1
            await asyncio.sleep(8)
            attempt_finished = True

        async def spy_close(self: KafkaHealthClient) -> None:
            closed.append(self)
            await real_close(self)

        config = KafkaConfiguration(bootstrap_servers=["broker-a.example:9093", "broker-b.example:9093"])
        started = time.monotonic()
        with (
            patch("syntara.integrations.lib.kafka_connection._PinnedKafkaConnection.connect", hang_create_conn),
            patch.object(KafkaHealthClient, "close", spy_close),
        ):
            result = await KafkaAdapter(config).validate(resolved_credential, timeout_seconds=1)
        elapsed = time.monotonic() - started

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT
        assert result.error == "Connection timed out after 1s"
        assert attempts == 1
        assert attempt_finished is False
        assert elapsed < 4
        assert len(closed) == 1


class TestKafkaConcurrentValidation:
    """Concurrent health checks leave module globals alone and keep caller deadlines."""

    @pytest.mark.asyncio
    async def test_overlapping_checks_never_replace_the_connection_factory(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        attempts = 0

        async def fail_connection(*_args: object, **_kwargs: object) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                entered.set()
                await release.wait()
            msg = "password rejected"
            raise AuthenticationFailedError(msg)

        original_factory = vars(aiokafka_client)["create_conn"]
        with patch("syntara.integrations.lib.kafka_connection._PinnedKafkaConnection.connect", fail_connection):
            first = asyncio.create_task(KafkaAdapter(kafka_config).validate(resolved_credential, 5))
            await entered.wait()
            second = asyncio.create_task(KafkaAdapter(kafka_config).validate(resolved_credential, 5))
            await asyncio.sleep(0)
            release.set()
            results = await asyncio.gather(first, second)
            assert vars(aiokafka_client)["create_conn"] is original_factory

            third = await KafkaAdapter(kafka_config).validate(resolved_credential, 5)
            assert vars(aiokafka_client)["create_conn"] is original_factory

        assert attempts == 3
        assert all(result.error_type == HealthCheckErrorType.AUTH_FAILURE for result in [*results, third])

    @pytest.mark.asyncio
    async def test_slow_check_does_not_delay_another_checks_timeout(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        attempts = 0
        closed: list[KafkaHealthClient] = []
        original_close = KafkaHealthClient.close

        async def wait_for_release(*_args: object, **_kwargs: object) -> None:
            nonlocal attempts
            attempts += 1
            entered.set()
            await release.wait()
            msg = "closed"
            raise KafkaConnectionError(msg)

        async def close_client(client: KafkaHealthClient) -> None:
            closed.append(client)
            await original_close(client)

        original_factory = vars(aiokafka_client)["create_conn"]
        with (
            patch("syntara.integrations.lib.kafka_connection._PinnedKafkaConnection.connect", wait_for_release),
            patch.object(KafkaHealthClient, "close", close_client),
        ):
            first = asyncio.create_task(KafkaAdapter(kafka_config).validate(resolved_credential, 5))
            await entered.wait()
            started = time.monotonic()
            try:
                second = await KafkaAdapter(kafka_config).validate(resolved_credential, 1)
                elapsed = time.monotonic() - started
                assert second.error_type == HealthCheckErrorType.TIMEOUT
                assert elapsed < 2
                assert not first.done()
                assert attempts == 2
            finally:
                release.set()
                await first
            assert vars(aiokafka_client)["create_conn"] is original_factory

        assert len(closed) == 2


class TestKafkaDiscover:
    """discover() is a connectivity check with no resources."""

    @pytest.mark.asyncio
    async def test_discover_delegates_to_validate(
        self, kafka_config: KafkaConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """A successful discover returns empty tool and model lists."""
        client = _client_mock()
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client):
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
        with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client) as constructor:
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


@pytest.mark.asyncio
@pytest.mark.parametrize(("protocol", "opt_in"), [("SSL", False), ("PLAINTEXT", True)])
async def test_unauthenticated_transport_does_not_require_a_login(protocol: str, *, opt_in: bool) -> None:
    config = KafkaConfiguration(bootstrap_servers=_BROKERS, security_protocol=protocol, allow_plaintext=opt_in)
    client = _client_mock()
    with patch("syntara.integrations.adapters.kafka.KafkaHealthClient", return_value=client) as constructor:
        result = await KafkaAdapter(config).validate({}, timeout_seconds=5)
    assert result.success
    assert constructor.call_args.kwargs["security_protocol"] == protocol
    assert constructor.call_args.kwargs["sasl_plain_username"] is None
    assert (constructor.call_args.kwargs["ssl_context"] is None) == (protocol == "PLAINTEXT")
