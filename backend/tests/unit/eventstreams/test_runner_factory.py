"""Runtime credential composition and Kafka construction outside database sessions."""

import ssl
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.exceptions import SafeValueError
from syntara.core.lib.encryption import SecretEncryptor
from syntara.eventstreams.adapters import runner_factory as module
from syntara.eventstreams.core.runtime import SubscriptionRuntimeError
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from tests.unit.eventstreams.test_connection_provider import connection_context


@pytest.mark.parametrize("skip_verification", [False, True])
@pytest.mark.parametrize("external_coordination", [False, True])
async def test_factory_reuses_existing_authentication_and_tls(monkeypatch, *, skip_verification, external_coordination):
    context = connection_context()
    context.session.__aenter__.return_value = context.session
    context.integration.configuration.insecure_skip_tls_verify = skip_verification
    monkeypatch.setattr(module, "SecretService", lambda *_args: context.secrets)
    monkeypatch.setattr(module, "EventConnectionProvider", lambda *_args, **_kwargs: context.provider)
    clients = []

    def client(connection, source, **kwargs: object) -> MagicMock:
        context.session.__aexit__.assert_awaited_once()
        assert connection.security_protocol == "SASL_SSL"
        assert connection.sasl_plain_username == SecretStr("PRIVATE_USER")
        assert connection.sasl_plain_password == SecretStr("PRIVATE_PASSWORD")
        assert connection.sasl_mechanism == context.integration.configuration.sasl_mechanism
        assert connection.ssl_context.verify_mode == (ssl.CERT_NONE if skip_verification else ssl.CERT_REQUIRED)
        assert source == context.snapshot.configuration
        assert kwargs["client_id"] == "test-worker"
        transport = MagicMock()
        clients.append(transport)
        return transport

    monkeypatch.setattr(module, "KafkaPartitionConsumer", client)
    runner = MagicMock()
    build_runner = MagicMock(return_value=runner)
    monkeypatch.setattr(module, "KafkaRecordRunner", build_runner)
    sessions = MagicMock(return_value=context.session)
    resources = EventWorkerResources()
    resources.gate = MagicMock()
    lookup = MagicMock()
    coordination = MagicMock() if external_coordination else None
    preparation, admission = MagicMock(), MagicMock()
    factory = module.ManagedRunnerFactory(
        sessions,
        preparation,
        admission,
        resources,
        SecretEncryptor(b"a" * 32),
        owner_worker_id="test-worker",
        lookup=lookup,
        cache_coordination=coordination,
    )
    assert await factory(context.snapshot) is runner
    assert len(clients) == 1
    clients[0].start.assert_not_called()
    assert build_runner.call_args.args == (context.snapshot, clients[0], sessions, preparation, admission)
    assert build_runner.call_args.kwargs["work_semaphore"] is resources.processing
    assert build_runner.call_args.kwargs["lookup"] is lookup
    assert build_runner.call_args.kwargs["gate"] is resources.gate
    assert build_runner.call_args.kwargs["cache_coordination"] is coordination


async def test_unavailable_binding_creates_no_transport_client(monkeypatch):
    context = connection_context()
    context.session.__aenter__.return_value = context.session
    context.integration.enabled = False
    monkeypatch.setattr(module, "SecretService", lambda *_args: context.secrets)
    monkeypatch.setattr(module, "EventConnectionProvider", lambda *_args, **_kwargs: context.provider)
    construct = MagicMock()
    monkeypatch.setattr(module, "KafkaPartitionConsumer", construct)
    factory = module.ManagedRunnerFactory(
        MagicMock(return_value=context.session),
        MagicMock(),
        MagicMock(),
        EventWorkerResources(),
        SecretEncryptor(b"a" * 32),
        owner_worker_id="test-worker",
    )
    with pytest.raises(SafeValueError, match="unavailable"):
        await factory(context.snapshot)
    construct.assert_not_called()
    context.session.__aexit__.assert_awaited_once()


async def test_database_resolution_failure_closes_shared_gate_and_is_transient(monkeypatch):
    context = connection_context()
    context.session.__aenter__.side_effect = SQLAlchemyError("isolated storage failure")
    construct = MagicMock()
    monkeypatch.setattr(module, "KafkaPartitionConsumer", construct)
    resources = EventWorkerResources()
    resources.gate = MagicMock()
    factory = module.ManagedRunnerFactory(
        MagicMock(return_value=context.session),
        MagicMock(),
        MagicMock(),
        resources,
        SecretEncryptor(b"a" * 32),
        owner_worker_id="test-worker",
    )
    with pytest.raises(SubscriptionRuntimeError) as failure:
        await factory(context.snapshot)
    assert failure.value.transient
    resources.gate.database_failed.assert_called_once()
    construct.assert_not_called()
