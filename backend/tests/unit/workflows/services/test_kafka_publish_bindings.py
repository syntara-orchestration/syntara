"""Publish bindings use the same actor and credential rules as other actions."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.credentials.exceptions import CredentialValidationError
from syntara.integrations.exceptions import IntegrationCredentialTypeMismatchError
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.fixture
def service() -> WorkflowService:
    return WorkflowService(AsyncMock(), MagicMock(id=uuid4()), MagicMock())


@pytest.fixture(autouse=True)
def login_validation() -> Iterator[AsyncMock]:
    with patch(
        "syntara.workflows.services.workflow_service.resolve_publish_kafka_login", new_callable=AsyncMock
    ) as login:
        yield login


@pytest.fixture
def definition() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "type": "kafka_publish",
                "parameters": {
                    "integration_id": str(uuid4()),
                    "credential_id": str(uuid4()),
                    "topic": "outcomes",
                    "payload": None,
                },
            }
        ]
    }


@pytest.mark.parametrize("visible", [True, False])
async def test_publish_requires_visible_integration_and_compatible_credential(
    service: WorkflowService,
    definition: dict[str, Any],
    *,
    visible: bool,
) -> None:
    session = service.session
    assert isinstance(session, AsyncMock)
    session.get.side_effect = [
        SimpleNamespace(
            enabled=True,
            integration_type="kafka",
            configuration=KafkaConfiguration(bootstrap_servers=["broker.example:9093"]),
        ),
        SimpleNamespace(enabled=True),
    ]
    with (
        patch.object(service, "_resolve_visible_integration_ids", return_value=None if visible else []),
        patch(
            "syntara.workflows.services.workflow_service.IntegrationService._validate_credential_type",
            new_callable=AsyncMock,
        ) as compatibility,
    ):
        if visible:
            await service._validate_kafka_publish_bindings(definition)
            compatibility.assert_awaited_once()
        else:
            with pytest.raises(SafeValueError, match="not visible"):
                await service._validate_kafka_publish_bindings(definition)
            session.get.assert_not_awaited()


@pytest.mark.parametrize("protocol", ["SASL_SSL", "SSL", "PLAINTEXT"])
@pytest.mark.parametrize("omit", [True, False])
async def test_runtime_credential_required_without_management_fallback(
    service: WorkflowService,
    definition: dict[str, Any],
    protocol: str,
    *,
    omit: bool,
) -> None:
    if omit:
        del definition["nodes"][0]["parameters"]["credential_id"]
    else:
        definition["nodes"][0]["parameters"]["credential_id"] = None
    session = service.session
    assert isinstance(session, AsyncMock)
    session.get.return_value = SimpleNamespace(
        enabled=True,
        integration_type="kafka",
        credential_id=uuid4(),
        configuration=KafkaConfiguration(
            bootstrap_servers=["broker.example:9093"],
            security_protocol=protocol,
            allow_plaintext=protocol == "PLAINTEXT",
        ),
    )
    with pytest.raises(SafeValueError, match="Select a runtime Kafka credential"):
        await service._validate_kafka_publish_bindings(definition)
    session.get.assert_not_awaited()


@pytest.mark.parametrize("protocol", ["SASL_SSL", "SSL", "PLAINTEXT"])
async def test_selected_credential_validated_for_connection_mode(
    service: WorkflowService,
    definition: dict[str, Any],
    protocol: str,
    login_validation: AsyncMock,
) -> None:
    session = service.session
    assert isinstance(session, AsyncMock)
    session.get.side_effect = [
        SimpleNamespace(
            enabled=True,
            integration_type="kafka",
            configuration=KafkaConfiguration(
                bootstrap_servers=["broker.example:9093"],
                security_protocol=protocol,
                allow_plaintext=protocol == "PLAINTEXT",
            ),
        ),
        SimpleNamespace(enabled=True),
    ]
    with (
        patch.object(service, "_resolve_visible_integration_ids", return_value=None),
        patch(
            "syntara.workflows.services.workflow_service.IntegrationService._validate_credential_type",
            new_callable=AsyncMock,
        ),
    ):
        await service._validate_kafka_publish_bindings(definition)
    assert login_validation.await_args is not None
    assert (
        str(login_validation.await_args.kwargs["runtime_credential_id"])
        == definition["nodes"][0]["parameters"]["credential_id"]
    )
    assert login_validation.await_args.kwargs["security_protocol"] == protocol


async def test_invalid_credential_contents_are_sanitized(
    service: WorkflowService,
    definition: dict[str, Any],
    login_validation: AsyncMock,
) -> None:
    session = service.session
    assert isinstance(session, AsyncMock)
    session.get.side_effect = [
        SimpleNamespace(
            enabled=True,
            integration_type="kafka",
            configuration=KafkaConfiguration(bootstrap_servers=["broker.example:9093"]),
        ),
        SimpleNamespace(enabled=True),
    ]
    login_validation.side_effect = CredentialValidationError("sensitive diagnostic")
    with (
        patch.object(service, "_resolve_visible_integration_ids", return_value=None),
        patch(
            "syntara.workflows.services.workflow_service.IntegrationService._validate_credential_type",
            new_callable=AsyncMock,
        ),
        pytest.raises(SafeValueError, match="missing fields required by the connection mode") as error,
    ):
        await service._validate_kafka_publish_bindings(definition)
    assert "sensitive diagnostic" not in str(error.value)


async def test_incompatible_runtime_credential_rejected(service: WorkflowService, definition: dict[str, Any]) -> None:
    session = service.session
    assert isinstance(session, AsyncMock)
    session.get.side_effect = [
        SimpleNamespace(
            enabled=True,
            integration_type="kafka",
            configuration=KafkaConfiguration(bootstrap_servers=["broker.example:9093"]),
        ),
        SimpleNamespace(enabled=True),
    ]
    with (
        patch.object(service, "_resolve_visible_integration_ids", return_value=None),
        patch(
            "syntara.workflows.services.workflow_service.IntegrationService._validate_credential_type",
            side_effect=IntegrationCredentialTypeMismatchError("kafka", "HTTP Basic Auth", frozenset({"Kafka"})),
        ),
        pytest.raises(IntegrationCredentialTypeMismatchError),
    ):
        await service._validate_kafka_publish_bindings(definition)


async def test_binding_checks_run_when_publish_has_no_credential(
    service: WorkflowService, definition: dict[str, Any]
) -> None:
    del definition["nodes"][0]["parameters"]["credential_id"]
    with patch.object(service, "_validate_kafka_publish_bindings", new_callable=AsyncMock) as bindings:
        await service._validate_credential_project_scope(definition, uuid4())
    bindings.assert_awaited_once_with(definition)


async def test_malformed_configuration_does_not_expose_payload(
    service: WorkflowService, definition: dict[str, Any]
) -> None:
    definition["nodes"][0]["parameters"].update(topic="${trigger.topic}", payload="sensitive payload")
    with pytest.raises(SafeValueError, match="literal Kafka topic") as error:
        await service._validate_kafka_publish_bindings(definition)
    assert "sensitive payload" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("parameters", [{}, {"integration_id": "", "credential_id": None, "topic": ""}])
async def test_draft_can_omit_connection_and_message_fields(
    service: WorkflowService, parameters: dict[str, Any]
) -> None:
    definition = {"nodes": [{"type": "kafka_publish", "parameters": parameters}]}
    await service._validate_kafka_publish_bindings(definition, allow_incomplete=True)
    assert isinstance(service.session, AsyncMock)
    service.session.get.assert_not_awaited()


async def test_draft_with_selected_integration_still_requires_visibility(service: WorkflowService) -> None:
    definition = {"nodes": [{"type": "kafka_publish", "parameters": {"integration_id": str(uuid4())}}]}
    with patch.object(service, "_resolve_visible_integration_ids", return_value=[]):
        with pytest.raises(SafeValueError, match="not visible"):
            await service._validate_kafka_publish_bindings(definition, allow_incomplete=True)


@pytest.mark.parametrize("enabled", [True, False])
async def test_draft_with_only_credential_checks_availability_and_type(
    service: WorkflowService, *, enabled: bool
) -> None:
    definition = {"nodes": [{"type": "kafka_publish", "parameters": {"credential_id": str(uuid4())}}]}
    assert isinstance(service.session, AsyncMock)
    service.session.get.return_value = SimpleNamespace(enabled=enabled)
    with patch(
        "syntara.workflows.services.workflow_service.IntegrationService._validate_credential_type",
        new_callable=AsyncMock,
    ) as compatibility:
        if enabled:
            await service._validate_kafka_publish_bindings(definition, allow_incomplete=True)
            compatibility.assert_awaited_once()
        else:
            with pytest.raises(SafeValueError, match="unavailable"):
                await service._validate_kafka_publish_bindings(definition, allow_incomplete=True)
            compatibility.assert_not_awaited()


async def test_malformed_draft_resource_reference_rejected_before_query(service: WorkflowService) -> None:
    definition = {"nodes": [{"type": "kafka_publish", "parameters": {"credential_id": "${trigger.credential}"}}]}
    with pytest.raises(SafeValueError, match="literal resource UUID"):
        await service._validate_credential_project_scope(definition, uuid4(), allow_incomplete_publish=True)
    assert isinstance(service.session, AsyncMock)
    service.session.exec.assert_not_awaited()
