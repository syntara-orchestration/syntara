"""Durable handoff tests against the migrated PostgreSQL schema."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.lib.encryption import SecretEncryptor
from syntara.workflow_runtime.completion import CompletionService
from syntara.workflow_runtime.contracts import ActivityError
from syntara.workflow_runtime.engines.temporal.registered_activities import CompletionDelivery
from syntara.workflow_runtime.models import ActivityCompletion


async def reserve(session: AsyncSession, encryptor: SecretEncryptor) -> ActivityCompletion:
    """Persist an attempt before its handler can expose a reference."""
    reference = uuid4()
    row = ActivityCompletion(
        id=reference,
        execution_id=uuid4(),
        project_id=uuid4(),
        node_execution_id="approval_iter_1",
        activity_name="approval.request",
        activity_version=1,
        engine_workflow_id="workflow",
        engine_run_id=str(uuid4()),
        attempt=1,
        encrypted_task_token=encryptor.encrypt_field("dG9rZW4=", str(reference), "task_token"),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_early_decision_survives_restart_and_waits_for_handoff(
    test_db_session: AsyncSession, test_db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A fresh delivery process sees the committed result but waits for Deferred."""
    encryptor = SecretEncryptor(bytes(range(32)))
    row = await reserve(test_db_session, encryptor)
    service = CompletionService(test_db_session)
    await service.complete(
        row.id, execution_id=row.execution_id, project_id=row.project_id, output={"decision": "approved"}
    )
    await test_db_session.commit()
    client = MagicMock()
    handle = MagicMock(complete=AsyncMock())
    client.get_async_activity_handle.return_value = handle
    delivery = CompletionDelivery(client, test_db_session_factory, encryptor)
    await delivery.deliver_pending()
    handle.complete.assert_not_called()
    row.deferred = True
    test_db_session.add(row)
    await test_db_session.commit()
    await CompletionDelivery(client, test_db_session_factory, encryptor).deliver_pending()
    handle.complete.assert_awaited_once_with({"output": {"decision": "approved"}}, rpc_timeout=timedelta(seconds=10))
    await test_db_session.refresh(row)
    assert row.state == "delivered"
    await delivery.deliver_pending()
    assert handle.complete.await_count == 1


@pytest.mark.asyncio
async def test_conflicts_scope_and_rollback(test_db_session: AsyncSession) -> None:
    """Acceptance is scoped, idempotent, and part of the business transaction."""
    row = await reserve(test_db_session, SecretEncryptor(bytes(range(32))))
    reference, execution_id, project_id = row.id, row.execution_id, row.project_id
    service = CompletionService(test_db_session)
    with pytest.raises(ActivityError, match="does not belong"):
        await service.complete(reference, execution_id=execution_id, project_id=uuid4(), output={})
    await service.complete(reference, execution_id=execution_id, project_id=project_id, output={"decision": "approved"})
    await test_db_session.rollback()
    await test_db_session.refresh(row)
    assert row.state == "reserved"
    for _ in range(2):
        await service.complete(
            reference, execution_id=execution_id, project_id=project_id, output={"decision": "approved"}
        )
    with pytest.raises(ActivityError, match="different outcome"):
        await service.complete(
            reference, execution_id=execution_id, project_id=project_id, output={"decision": "rejected"}
        )


@pytest.mark.asyncio
async def test_missing_engine_attempt_is_not_reported_as_delivered(
    test_db_session: AsyncSession, test_db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A timeout and a lost delivery acknowledgement must not be conflated."""
    encryptor = SecretEncryptor(bytes(range(32)))
    row = await reserve(test_db_session, encryptor)
    await CompletionService(test_db_session).complete(
        row.id, execution_id=row.execution_id, project_id=row.project_id, output={}
    )
    row.deferred = True
    test_db_session.add(row)
    await test_db_session.commit()
    client = MagicMock()
    client.get_async_activity_handle.return_value.complete = AsyncMock(
        side_effect=RPCError("attempt not found", RPCStatusCode.NOT_FOUND, b"")
    )
    await CompletionDelivery(client, test_db_session_factory, encryptor).deliver_pending()
    await test_db_session.refresh(row)
    assert row.state == "unconfirmed"
    assert row.output == {}


@pytest.mark.asyncio
async def test_expired_reference_cannot_complete(test_db_session: AsyncSession) -> None:
    """A late decision cannot revive an expired attempt."""
    row = await reserve(test_db_session, SecretEncryptor(bytes(range(32))))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    test_db_session.add(row)
    await test_db_session.commit()
    with pytest.raises(ActivityError, match="expired"):
        await CompletionService(test_db_session).complete(
            row.id, execution_id=row.execution_id, project_id=row.project_id, output={"decision": "approved"}
        )
