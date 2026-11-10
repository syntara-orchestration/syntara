"""Preparation freezes the selected identity and applies safe preflight failures."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiokafka import errors
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities import kafka_publish_connection as module


@pytest.mark.parametrize("partition_error", [0, errors.LeaderNotAvailableError.errno])
async def test_preflight_checks_partition_errors_without_creating_topics(
    monkeypatch: pytest.MonkeyPatch,
    partition_error: int,
) -> None:
    connection = MagicMock()
    connection.send = AsyncMock(
        return_value=SimpleNamespace(brokers=[], topics=[(0, "outcomes", False, [(partition_error, 0, 1, [1], [1])])])
    )
    monkeypatch.setattr(module, "_connect", AsyncMock(return_value=connection))
    close = AsyncMock()
    monkeypatch.setattr(module, "_close", close)
    monkeypatch.setattr(module, "validate_integration_configuration_no_ssrf", MagicMock())
    config = KafkaConfiguration(bootstrap_servers=["broker.example:9093"], security_protocol="SSL")
    if partition_error:
        with pytest.raises(errors.LeaderNotAvailableError):
            await module.check_publish_topic(config, {}, "outcomes")
    else:
        await module.check_publish_topic(config, {}, "outcomes")
    request = connection.send.call_args.args[0].prepare({3: (4, 4)})
    assert request.allow_auto_topic_creation is False
    close.assert_awaited_once_with(connection)


async def test_expired_preparation_does_not_touch_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    resources = AsyncMock()
    monkeypatch.setattr(module, "current_publish_resources", resources)
    with pytest.raises(ApplicationError) as error:
        await ActivityEnvironment().run(
            module.prepare_kafka_publish, {}, str(uuid4()), 30, (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        )
    assert error.value.type == "kafka_timeout"
    resources.assert_not_awaited()


async def test_each_invocation_resolves_selected_credential_once(monkeypatch: pytest.MonkeyPatch) -> None:
    config = KafkaConfiguration(bootstrap_servers=["broker.example:9093"])
    context = MagicMock()
    context.return_value.__aenter__ = AsyncMock()
    context.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module, "_session_factory", context)
    monkeypatch.setattr(module, "current_publish_resources", AsyncMock(return_value=(config, "revision")))
    monkeypatch.setattr(module, "create_secret_service", MagicMock())
    preflight = AsyncMock()
    monkeypatch.setattr(module, "check_publish_topic", preflight)
    selected = str(uuid4())
    credentials = AsyncMock(
        side_effect=[
            {"extra_vars": {"kafka_password": "original"}},
            {"extra_vars": {"kafka_password": "rotated"}},
        ]
    )
    monkeypatch.setattr(module, "_resolve_single_credential", credentials)
    parameters = {"integration_id": str(uuid4()), "credential_id": selected, "topic": "outcomes", "payload": None}
    env = ActivityEnvironment()
    first = await env.run(module.prepare_kafka_publish, parameters, "project")
    second = await env.run(module.prepare_kafka_publish, parameters, "project")
    assert first["_resolved_credentials"] == {"extra_vars": {"kafka_password": "original"}}
    assert second["_resolved_credentials"] == {"extra_vars": {"kafka_password": "rotated"}}
    assert credentials.await_count == 2
    assert all(call.args[3] == selected for call in credentials.await_args_list)


@pytest.mark.parametrize("protocol", ["SSL", "PLAINTEXT"])
async def test_non_sasl_preparation_binds_credential_without_sasl_fields(
    monkeypatch: pytest.MonkeyPatch, protocol: str
) -> None:
    config = KafkaConfiguration(
        bootstrap_servers=["broker.example:9093"], security_protocol=protocol, allow_plaintext=protocol == "PLAINTEXT"
    )
    context = MagicMock()
    context.return_value.__aenter__ = AsyncMock()
    context.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module, "_session_factory", context)
    monkeypatch.setattr(module, "current_publish_resources", AsyncMock(return_value=(config, "revision")))
    credentials = AsyncMock()
    monkeypatch.setattr(module, "_resolve_single_credential", credentials)
    preflight = AsyncMock()
    monkeypatch.setattr(module, "check_publish_topic", preflight)
    selected = str(uuid4())
    prepared = await ActivityEnvironment().run(
        module.prepare_kafka_publish,
        {"integration_id": str(uuid4()), "credential_id": selected, "topic": "outcomes", "payload": None},
        "project",
    )
    assert prepared["_resolved_credentials"] == {
        "credential_id": selected,
        "credential_type_name": "Kafka",
        "extra_vars": {},
        "_secret_values": [],
    }
    credentials.assert_not_awaited()
    preflight.assert_awaited_once_with(config, {}, "outcomes")
