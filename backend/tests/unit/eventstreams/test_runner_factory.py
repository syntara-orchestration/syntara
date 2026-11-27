"""Runtime credential composition and Kafka construction outside database sessions."""

import ssl
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.exceptions import SafeValueError
from syntara.core.lib.encryption import SecretEncryptor
from syntara.credentials.lib.kafka_connection import KafkaSecurityProtocol
from syntara.credentials.lib.preseed import GA_CREDENTIAL_TYPES, MTLS_CLIENT_IDENTITY_TYPE_NAME
from syntara.credentials.models.credential import Credential
from syntara.eventstreams.adapters import runner_factory as module
from syntara.eventstreams.core.runtime import RuntimeFailureCode, SubscriptionRuntimeError
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.integrations.adapters.kafka import KafkaAuthenticationConfigurationError
from syntara.integrations.adapters.kafka_tls import KafkaMTLSContext
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from tests.fixtures.tls import generate_self_signed_cert
from tests.unit.eventstreams.test_connection_provider import connection_context


async def test_factory_uses_runtime_identity_and_retains_group(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = connection_context()
    context.session.__aenter__.return_value = context.session
    config = context.integration.configuration
    assert isinstance(config, KafkaConfiguration)
    config.security_protocol = KafkaSecurityProtocol.SSL
    context.integration.management_credential_id = uuid4()
    identity_type = next(item for item in GA_CREDENTIAL_TYPES if item["name"] == MTLS_CLIENT_IDENTITY_TYPE_NAME)
    context.credential_type.name = identity_type["name"]
    context.credential_type.injectors = identity_type["injectors"]
    certificate, private_key = generate_self_signed_cert(tmp_path, "runtime identity", "runtime")
    context.secrets.retrieve_secret.return_value = {
        "client_certificate": certificate.read_text(),
        "client_private_key": private_key.read_text(),
    }
    monkeypatch.setattr(module, "SecretService", lambda *_args: context.secrets)
    monkeypatch.setattr(module, "EventConnectionProvider", lambda *_args, **_kwargs: context.provider)
    construct = MagicMock()
    monkeypatch.setattr(module, "KafkaPartitionConsumer", construct)
    monkeypatch.setattr(module, "KafkaRecordRunner", MagicMock())
    factory = module.ManagedRunnerFactory(
        MagicMock(return_value=context.session),
        MagicMock(),
        MagicMock(),
        EventWorkerResources(),
        SecretEncryptor(b"a" * 32),
        owner_worker_id="test-worker",
    )
    before = await factory.connection_revision(context.snapshot)
    await factory(context.snapshot)
    connection, source = construct.call_args.args
    assert isinstance(connection.ssl_context, KafkaMTLSContext)
    assert connection.ssl_context.check_hostname
    assert source.group_id == context.snapshot.configuration.group_id
    assert all(call.args[0] == context.credential.secret_id for call in context.secrets.retrieve_secret.await_args_list)
    assert all(
        call.args[1] == context.snapshot.runtime_credential_id
        for call in context.session.get.await_args_list
        if call.args[0] is Credential
    )

    context.session.exec.return_value.one_or_none.return_value += timedelta(microseconds=1)
    assert await factory.connection_revision(context.snapshot) != before
    context.credential.enabled = False
    with pytest.raises(SafeValueError, match="runtime credential is unavailable"):
        await factory.connection_revision(context.snapshot)


@pytest.mark.parametrize("skip_verification", [False, True])
@pytest.mark.parametrize("protocol", list(KafkaSecurityProtocol))
async def test_factory_reuses_existing_authentication_and_tls(monkeypatch, protocol, *, skip_verification):
    context = connection_context()
    context.session.__aenter__.return_value = context.session
    context.integration.configuration.insecure_skip_tls_verify = skip_verification
    context.integration.configuration.security_protocol = protocol
    context.integration.configuration.allow_plaintext = protocol == KafkaSecurityProtocol.PLAINTEXT
    monkeypatch.setattr(module, "SecretService", lambda *_args: context.secrets)
    monkeypatch.setattr(module, "EventConnectionProvider", lambda *_args, **_kwargs: context.provider)
    clients = []

    def client(connection, source, **kwargs: object) -> MagicMock:
        context.session.__aexit__.assert_awaited_once()
        assert connection.security_protocol == protocol
        if protocol == KafkaSecurityProtocol.SASL_SSL:
            assert connection.sasl_plain_username == SecretStr("PRIVATE_USER")
            assert connection.sasl_plain_password == SecretStr("PRIVATE_PASSWORD")
            assert connection.sasl_mechanism == context.integration.configuration.sasl_mechanism
        else:
            assert connection.sasl_plain_username is None
            assert connection.sasl_plain_password is None
            assert connection.sasl_mechanism is None
        if protocol == KafkaSecurityProtocol.PLAINTEXT:
            assert connection.ssl_context is None
        else:
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
    preparation, admission = MagicMock(), MagicMock()
    factory = module.ManagedRunnerFactory(
        sessions,
        preparation,
        admission,
        resources,
        SecretEncryptor(b"a" * 32),
        owner_worker_id="test-worker",
    )
    assert await factory(context.snapshot) is runner
    assert len(clients) == 1
    clients[0].start.assert_not_called()
    assert build_runner.call_args.args == (context.snapshot, clients[0], sessions, preparation, admission)
    assert build_runner.call_args.kwargs["work_semaphore"] is resources.processing
    assert build_runner.call_args.kwargs["gate"] is resources.gate


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


async def test_factory_sanitizes_authentication_configuration_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = module.ManagedRunnerFactory(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        EventWorkerResources(),
        SecretEncryptor(b"a" * 32),
        owner_worker_id="test-worker",
    )
    monkeypatch.setattr(
        factory,
        "resolve_connection",
        AsyncMock(side_effect=KafkaAuthenticationConfigurationError("underlying error detail")),
    )
    construct = MagicMock()
    monkeypatch.setattr(module, "KafkaPartitionConsumer", construct)

    with pytest.raises(SubscriptionRuntimeError) as failure:
        await factory(connection_context().snapshot)

    assert failure.value.code == RuntimeFailureCode.CONFIGURATION_UNAVAILABLE
    assert str(failure.value) == RuntimeFailureCode.CONFIGURATION_UNAVAILABLE.value
    assert failure.value.__suppress_context__
    construct.assert_not_called()


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


@pytest.mark.parametrize("changed", ["integration", "credential", "credential_type", "secret"])
async def test_connection_revision_reads_existing_resource_changes_without_constructing_consumer(monkeypatch, changed):
    context = connection_context()
    context.session.__aenter__.return_value = context.session
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
    before = await factory.connection_revision(context.snapshot)
    if changed == "secret":
        context.session.exec.return_value.one_or_none.return_value += timedelta(microseconds=1)
    else:
        getattr(context, changed).updated_at += timedelta(microseconds=1)
    after = await factory.connection_revision(context.snapshot)
    assert before != after
    assert "PRIVATE" not in before + after
    assert context.session.__aexit__.await_count == 2
    construct.assert_not_called()


async def test_connection_revision_database_failure_closes_shared_gate(monkeypatch):
    context = connection_context()
    context.session.__aenter__.side_effect = SQLAlchemyError("unavailable")
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
    with pytest.raises(SQLAlchemyError):
        await factory.connection_revision(context.snapshot)
    resources.gate.database_failed.assert_called_once()
