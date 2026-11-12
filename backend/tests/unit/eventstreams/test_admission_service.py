"""Temporal-first scheduling with isolated normal Execution transactions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError

from syntara.eventstreams.core.deduplication import TemporalAcceptance
from syntara.eventstreams.core.handler import BlockedDelivery, EventLaunchError, ResolvedDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import AcceptedWorkflow, PreparedExecution
from syntara.eventstreams.services import admission_service as module
from syntara.eventstreams.services.admission_service import EventAdmissionService
from tests.helpers.eventstream_sessions import session_factory
from tests.unit.eventstreams.test_execution_preparation_service import preparation_context
from tests.unit.eventstreams.test_record_processing_service import terminal


@pytest_asyncio.fixture
async def scheduling(monkeypatch):
    prepared = await preparation_context(monkeypatch).prepare()
    assert isinstance(prepared, PreparedExecution)
    accepted = AcceptedWorkflow.model_validate(
        {
            "identity": prepared.identity,
            "temporal_run_id": "accepted-run",
            "arguments": tuple(prepared.workflow_arguments()),
        },
        strict=True,
    )
    factory, sessions = session_factory()
    store = SimpleNamespace(
        lookup=AsyncMock(return_value=None), persist=AsyncMock(return_value=terminal(prepared.identity).terminal)
    )
    monkeypatch.setattr(module, "EventExecutionStore", lambda _session: store)
    launcher = SimpleNamespace(
        start=AsyncMock(return_value=accepted.acceptance),
        lookup=AsyncMock(side_effect=EventLaunchError(SchedulingFailureCode.TEMPORAL_NOT_FOUND)),
    )
    return SimpleNamespace(
        prepared=prepared,
        accepted=accepted,
        sessions=sessions,
        store=store,
        launcher=launcher,
        service=EventAdmissionService(factory, launcher),
    )


async def test_start_precedes_execution_write_and_resolution_follows_commit(scheduling) -> None:
    context = scheduling

    async def start(_prepared: PreparedExecution) -> TemporalAcceptance:
        assert context.sessions == []
        context.store.persist.assert_not_awaited()
        assert isinstance(context.accepted.acceptance, TemporalAcceptance)
        return context.accepted.acceptance

    context.launcher.start.side_effect = start
    result = await context.service.schedule(context.prepared)
    assert isinstance(result, ResolvedDelivery)
    assert len(context.sessions) == 1
    context.sessions[0].begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)


async def test_failed_start_does_not_write_execution(scheduling) -> None:
    context = scheduling
    context.launcher.start.side_effect = EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE)
    result = await context.service.schedule(context.prepared)
    assert not isinstance(result, ResolvedDelivery)
    context.store.persist.assert_not_awaited()
    assert context.sessions == []


async def test_lost_start_response_recovers_original_arguments(scheduling) -> None:
    context = scheduling
    context.launcher.start.side_effect = EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE)
    context.launcher.lookup.side_effect = None
    context.launcher.lookup.return_value = context.accepted
    assert isinstance(await context.service.schedule(context.prepared), ResolvedDelivery)
    saved = context.store.persist.call_args.args[0]
    assert saved.workflow_arguments() == context.prepared.workflow_arguments()
    context.launcher.start.assert_awaited_once()


async def test_normal_execution_is_checked_before_temporal(scheduling) -> None:
    context = scheduling
    context.store.lookup.return_value = terminal(context.prepared.identity).terminal
    assert isinstance(await context.service.recover_accepted(context.prepared.identity), ResolvedDelivery)
    context.launcher.lookup.assert_not_awaited()
    context.launcher.start.assert_not_awaited()


async def test_only_confirmed_absence_allows_new_preparation(scheduling) -> None:
    assert await scheduling.service.recover_accepted(scheduling.prepared.identity) is None
    scheduling.launcher.lookup.side_effect = EventLaunchError(SchedulingFailureCode.HISTORY_UNAVAILABLE)
    result = await scheduling.service.recover_accepted(scheduling.prepared.identity)
    assert result is not None
    assert not isinstance(result, ResolvedDelivery)
    scheduling.launcher.start.assert_not_awaited()


async def test_database_failure_retries_same_execution_without_restarting(scheduling) -> None:
    context = scheduling
    statement = "lost commit response"
    context.store.persist.side_effect = [
        OperationalError(statement, {}, RuntimeError("PRIVATE")),
        context.store.persist.return_value,
    ]
    assert isinstance(await context.service.schedule(context.prepared), ResolvedDelivery)
    assert len(context.sessions) == 2
    assert context.store.persist.call_args_list[0].args == context.store.persist.call_args_list[1].args
    context.launcher.start.assert_awaited_once()


async def test_repeated_database_failure_keeps_acceptance_unresolved(scheduling) -> None:
    context = scheduling
    statement = "database unavailable"
    context.store.persist.side_effect = OperationalError(statement, {}, RuntimeError("PRIVATE"))
    result = await context.service.schedule(context.prepared)
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == SchedulingFailureCode.STORAGE_UNAVAILABLE
    context.launcher.start.assert_awaited_once()


@pytest.mark.parametrize("entrypoint", ["lookup", "persist", "persist_retry"])
async def test_invalid_evidence_type_blocks_recovery_or_confirmation(scheduling, entrypoint) -> None:
    context = scheduling
    message = "Invalid retained scheduling evidence"
    failure = TypeError(message)
    if entrypoint == "lookup":
        context.store.lookup.side_effect = failure
        result = await context.service.recover_accepted(context.prepared.identity)
        context.launcher.lookup.assert_not_awaited()
        context.launcher.start.assert_not_awaited()
    else:
        context.store.persist.side_effect = (
            [OperationalError(message, {}, RuntimeError(message)), failure]
            if entrypoint == "persist_retry"
            else failure
        )
        result = await context.service.schedule(context.prepared)
        context.launcher.start.assert_awaited_once()
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == SchedulingFailureCode.EVIDENCE_MISMATCH
