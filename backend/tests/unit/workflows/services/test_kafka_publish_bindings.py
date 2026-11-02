"""Publish bindings use the same actor and credential rules as other actions."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.integrations.exceptions import IntegrationCredentialTypeMismatchError
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.fixture
def service() -> WorkflowService:
    return WorkflowService(AsyncMock(), MagicMock(id=uuid4()), MagicMock())


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
async def test_runtime_credential_requirement_uses_transport_without_management_fallback(
    service: WorkflowService,
    definition: dict[str, Any],
    protocol: str,
) -> None:
    del definition["nodes"][0]["parameters"]["credential_id"]
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
    with patch.object(service, "_resolve_visible_integration_ids", return_value=None):
        if protocol == "SASL_SSL":
            with pytest.raises(SafeValueError, match="runtime Kafka credential"):
                await service._validate_kafka_publish_bindings(definition)
        else:
            await service._validate_kafka_publish_bindings(definition)
    assert session.get.await_count == 1


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
