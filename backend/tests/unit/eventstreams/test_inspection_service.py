"""Denied references must stop preflight before decryption or broker access."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.services.inspection_service import EventSubscriptionInspectionService

MODULE = "syntara.eventstreams.services.inspection_service"


@pytest.fixture
def service() -> EventSubscriptionInspectionService:
    """Request services with strictly mocked database and resource boundaries."""
    instance = EventSubscriptionInspectionService(AsyncMock(), MagicMock(), MagicMock(), MagicMock())
    instance.workflows = MagicMock()
    instance.workflows.get_workflow_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid4(), project_id=uuid4()))
    instance.workflows.validate_event_subscribe_access = AsyncMock()
    instance.integrations = MagicMock()
    instance.integrations.resolve_credential = AsyncMock()
    return instance


async def test_denied_reference_never_decrypts_or_connects(service: EventSubscriptionInspectionService) -> None:
    params = KafkaSubscribeParameters(topic="alerts", integration_id=uuid4(), credential_id=uuid4())
    cast("MagicMock", service.workflows).validate_event_subscribe_access.side_effect = AuthorizationDeniedError(
        "Denied"
    )
    with patch(f"{MODULE}.test_kafka_connection") as probe, pytest.raises(AuthorizationDeniedError):
        await service.test_unsaved(uuid4(), params)
    cast("MagicMock", service.integrations).resolve_credential.assert_not_called()
    probe.assert_not_called()
