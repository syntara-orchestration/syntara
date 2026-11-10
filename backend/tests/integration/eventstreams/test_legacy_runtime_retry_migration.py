"""Legacy availability failures become due without resetting frozen execution state."""

import importlib
from datetime import datetime, timedelta
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func
from sqlalchemy.engine import Connection
from sqlmodel import select

from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.core.deduplication import DeliveryClaim
from syntara.eventstreams.core.handler import ResolvedDelivery, SchedulingFailureCode
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.workflows.models.execution import Execution
from tests.integration.eventstreams import test_execution_scheduling

pytestmark = pytest.mark.integration
scheduling_context = test_execution_scheduling.scheduling_context
MIGRATION = "syntara.core.database.migrations.versions.b7e32a91c604_retry_legacy_runtime_unavailable"


async def upgrade(context) -> None:
    migration = importlib.import_module(MIGRATION)

    def apply(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    async with context.delivery.session_factory() as session, session.begin():
        connection = await session.connection()
        await connection.run_sync(apply)


async def park(context, code: SchedulingFailureCode, *, permanently: bool = True) -> None:
    async with context.delivery.session_factory() as session, session.begin():
        now = (await session.exec(select(func.clock_timestamp()))).one()
        retry_at = EventDeliveryDefaults.NO_AUTOMATIC_RETRY_AT if permanently else now + timedelta(minutes=5)
        result = await context.delivery.store(session).record_scheduling_failure(
            context.prepared.claim, next_attempt_at=retry_at, error_code=code.value
        )
        assert isinstance(result, DeliveryClaim)


async def saved(context) -> tuple[dict[str, Any], dict[str, Any]]:
    async with context.delivery.session_factory() as session:
        delivery = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert delivery is not None
        assert execution is not None
        return delivery.model_dump(), execution.model_dump()


async def test_upgrade_wakes_only_legacy_availability_failure_and_recovers_same_execution(scheduling_context) -> None:
    context = scheduling_context
    await park(context, SchedulingFailureCode.RUNTIME_UNAVAILABLE)
    before_delivery, before_execution = await saved(context)
    assert await context.recovery.recover_due("before-upgrade", limit=1) == []

    await upgrade(context)

    after_delivery, after_execution = await saved(context)
    assert after_delivery["next_attempt_at"] < EventDeliveryDefaults.NO_AUTOMATIC_RETRY_AT
    assert after_delivery == {**before_delivery, "next_attempt_at": after_delivery["next_attempt_at"]}
    metadata = after_execution["execution_metadata"]["event_delivery"]
    assert datetime.fromisoformat(metadata["next_attempt_at"]) == after_delivery["next_attempt_at"]
    expected_metadata = {
        **before_execution["execution_metadata"],
        "event_delivery": {
            **before_execution["execution_metadata"]["event_delivery"],
            "next_attempt_at": metadata["next_attempt_at"],
        },
    }
    assert after_execution == {**before_execution, "execution_metadata": expected_metadata}
    # Applying the data correction again cannot move an already due timestamp.
    await upgrade(context)
    assert await saved(context) == (after_delivery, after_execution)

    results = await context.recovery.recover_due("after-upgrade", limit=1)
    assert len(results) == 1
    assert isinstance(results[0][1], ResolvedDelivery)
    assert len(context.temporal.starts) == 1
    started = context.temporal.starts[0]
    assert started.execution_id == context.prepared.execution_id
    assert started.claim.binding == context.prepared.claim.binding
    assert started.workflow_arguments() == context.prepared.workflow_arguments()


@pytest.mark.parametrize(
    ("code", "permanently"),
    [
        (SchedulingFailureCode.EVIDENCE_MISMATCH, True),
        (SchedulingFailureCode.HISTORY_EXPIRED, True),
        (SchedulingFailureCode.RUNTIME_UNAVAILABLE, False),
    ],
)
async def test_upgrade_preserves_other_failure_and_backoff_state(
    scheduling_context, code, *, permanently: bool
) -> None:
    context = scheduling_context
    await park(context, code, permanently=permanently)
    before = await saved(context)
    await upgrade(context)
    assert await saved(context) == before
    assert await context.recovery.recover_due("unchanged", limit=1) == []
    assert context.temporal.starts == []
