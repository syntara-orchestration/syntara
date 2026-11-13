"""Real PostgreSQL preparation transactions; no broker or Temporal acceptance claims."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func
from sqlmodel import select

from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader, WorkflowEventEnvelope
from syntara.eventstreams.core.preparation import PreparationBlocked, PreparedExecution
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encoded_envelope_size
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.workflows.models.execution import Execution, ExecutionStatus

if TYPE_CHECKING:
    from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def preparation_context(delivery_context: DeliveryContext) -> DeliveryContext:
    """Complete the fixture's runtime credential through the real secret service."""
    context = delivery_context
    async with context.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.snapshot.runtime_credential_id)
        assert credential is not None
        credential.secret_id = await create_secret_service(session).create_secret(
            {"username": "test", "password": "test"}
        )
        credential_type = await session.get(CredentialType, credential.credential_type_id)
        assert credential_type is not None
        credential_type.injectors = {"extra_vars": {"kafka_username": "{{username}}", "kafka_password": "{{password}}"}}
    return context


async def envelope(context: DeliveryContext, *, offset: int = 0) -> WorkflowEventEnvelope:
    async with context.session_factory() as session:
        now = (await session.exec(select(func.clock_timestamp()))).one()
    result = JsonEventDecoder().decode(
        RawEvent(
            value=b' {"count":2} \n',
            key=b"\xff",
            headers=(RawEventHeader(name="repeat", value=None), RawEventHeader(name="repeat", value=b"")),
            source_metadata=KafkaSourceMetadata(
                integration_id=context.snapshot.integration_identity,
                subscription_id=context.snapshot.subscription_id,
                source_generation=context.snapshot.source_generation,
                received_at=now,
                topic=context.snapshot.configuration.topic,
                partition=0,
                offset=str(offset),
            ),
        )
    )
    assert isinstance(result, EventDecodeSuccess)
    return result.envelope


def service(context: DeliveryContext) -> EventExecutionPreparationService:
    return EventExecutionPreparationService(context.session_factory)


async def test_preparation_never_creates_execution_before_temporal_acceptance(
    preparation_context: DeliveryContext,
) -> None:
    context = preparation_context
    result = await service(context).prepare_delivery(context.snapshot, context.identity(), await envelope(context))
    assert isinstance(result, PreparedExecution)
    async with context.session_factory() as session:
        assert await session.get(Execution, result.execution_id) is None
    assert result.binding.execution_principal_id == context.principal_id
    assert result.execution().status == ExecutionStatus.PENDING


async def test_complete_start_arguments_are_limited_before_persistence(preparation_context, override_settings) -> None:
    context = preparation_context
    value = await envelope(context)
    with override_settings(event_max_envelope_bytes=encoded_envelope_size(value) + 1):
        result = await service(context).prepare_delivery(context.snapshot, context.identity(), value)
    assert isinstance(result, EventDecodeFailure)
    async with context.session_factory() as session:
        assert await session.get(Execution, context.identity().execution_id) is None


async def test_unavailable_runtime_authentication_does_not_create_execution(preparation_context) -> None:
    context = preparation_context
    async with context.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.snapshot.runtime_credential_id)
        assert credential is not None
        credential.enabled = False
    result = await service(context).prepare_delivery(context.snapshot, context.identity(), await envelope(context))
    assert isinstance(result, PreparationBlocked)
    async with context.session_factory() as session:
        assert await session.get(Execution, context.identity().execution_id) is None


async def test_production_revision_changes_on_secret_update(preparation_context) -> None:
    context = preparation_context
    async with context.session_factory() as session:
        before = await EventConnectionProvider(session).resolve_revision(context.snapshot)
    async with context.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.snapshot.runtime_credential_id)
        assert credential is not None
        assert credential.secret_id is not None
        await create_secret_service(session).update_secret(
            credential.secret_id, {"username": "test", "password": uuid4().hex}
        )
    async with context.session_factory() as session:
        after = await EventConnectionProvider(session).resolve_revision(context.snapshot)
    assert after.digest != before.digest
