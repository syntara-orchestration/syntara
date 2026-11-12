"""Temporal adapter policies and signed frozen evidence with isolated RPCs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from temporalio.api.common.v1 import Header, Payloads, WorkflowType
from temporalio.api.history.v1 import HistoryEvent, WorkflowExecutionStartedEventAttributes
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.converter import DataConverter
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from syntara.eventstreams.core.handler import EventLaunchError, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.handlers.workflow_launcher import TemporalWorkflowLauncher
from syntara.workflows.workflow_engine import workflow_auth
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.unit.eventstreams.test_execution_preparation_service import preparation_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass
class LauncherContext:
    """Frozen preparation plus isolated Temporal response objects."""

    prepared: PreparedExecution
    launcher: TemporalWorkflowLauncher
    client: MagicMock
    handle: MagicMock
    event: HistoryEvent
    description: SimpleNamespace


@pytest_asyncio.fixture
async def launcher_context(monkeypatch: pytest.MonkeyPatch) -> LauncherContext:
    monkeypatch.setattr(workflow_auth, "_signing_key", b"test-signing-key")
    prepared = await preparation_context(monkeypatch).prepare()
    assert isinstance(prepared, PreparedExecution)
    arguments = prepared.workflow_arguments()
    event = HistoryEvent(
        event_id=1,
        workflow_execution_started_event_attributes=WorkflowExecutionStartedEventAttributes(
            workflow_type=WorkflowType(name="orchestrator_workflow"),
            input=Payloads(payloads=DataConverter.default.payload_converter.to_payloads(arguments)),
            header=Header(
                fields=workflow_auth.build_auth_header(
                    prepared.temporal_workflow_id, "orchestrator_workflow", arguments
                )
            ),
        ),
    )
    description = SimpleNamespace(
        id=prepared.temporal_workflow_id,
        run_id="accepted-run",
        workflow_type="orchestrator_workflow",
        task_queue="user",
    )
    handle = MagicMock(first_execution_run_id="accepted-run")
    handle.describe = AsyncMock(return_value=description)

    async def events() -> AsyncIterator[HistoryEvent]:
        yield event

    handle.fetch_history_events.side_effect = lambda **_kwargs: events()
    client = MagicMock()
    client.namespace = "test"
    client.data_converter = DataConverter.default
    client.start_workflow = AsyncMock(return_value=handle)
    client.get_workflow_handle.return_value = handle
    launcher = TemporalWorkflowLauncher(TemporalExecutionService(client, "user", background_task_queue="builtin"))
    return LauncherContext(prepared, launcher, client, handle, event, description)


@pytest.mark.parametrize(("builtin", "queue"), [(False, "user"), (True, "builtin")])
async def test_start_uses_frozen_arguments_and_explicit_policies(launcher_context, *, builtin, queue) -> None:
    context = launcher_context
    prepared = context.prepared.model_copy(update={"is_builtin": builtin})
    accepted = await context.launcher.start(prepared)
    kwargs = context.client.start_workflow.call_args.kwargs
    assert kwargs["id"] == prepared.identity.temporal_workflow_id
    assert kwargs["args"] == prepared.workflow_arguments()
    assert kwargs["task_queue"] == queue
    assert kwargs["id_reuse_policy"] == WorkflowIDReusePolicy.REJECT_DUPLICATE
    assert kwargs["id_conflict_policy"] == WorkflowIDConflictPolicy.FAIL
    assert accepted.execution_id == prepared.execution_id
    assert accepted.input_fingerprint == prepared.binding.input_fingerprint
    assert accepted.temporal_run_id == "accepted-run"
    context.handle.cancel.assert_not_called()


async def test_already_started_verifies_pinned_signed_history(launcher_context) -> None:
    context = launcher_context
    context.client.start_workflow.side_effect = WorkflowAlreadyStartedError(
        context.prepared.temporal_workflow_id, "orchestrator_workflow", run_id="accepted-run"
    )
    accepted = await context.launcher.start(context.prepared)
    assert accepted.temporal_run_id == "accepted-run"
    assert all(call.kwargs["run_id"] == "accepted-run" for call in context.client.get_workflow_handle.call_args_list)
    assert context.handle.fetch_history_events.call_args.kwargs["page_size"] == 1
    assert context.handle.fetch_history_events.call_args.kwargs["skip_archival"] is True
    context.handle.cancel.assert_not_called()


async def test_lookup_recovers_original_arguments_without_a_preparation(launcher_context) -> None:
    context = launcher_context
    accepted = await context.launcher.lookup(context.prepared.identity)
    recovered = accepted.preparation()
    assert recovered.workflow_arguments() == context.prepared.workflow_arguments()
    assert recovered.binding == context.prepared.binding
    assert accepted.acceptance.temporal_run_id == "accepted-run"
    context.client.start_workflow.assert_not_awaited()
    assert context.client.get_workflow_handle.call_args.kwargs["run_id"] == "accepted-run"


@pytest.mark.parametrize(
    "mismatch",
    ["execution", "identity", "version", "principal", "source", "event_type", "context_type", "coordinates_type"],
)
async def test_lookup_rejects_signed_arguments_for_inconsistent_event_coordinates(launcher_context, mismatch) -> None:
    context = launcher_context
    arguments = deepcopy(context.prepared.workflow_arguments())
    metadata = arguments[8]
    assert isinstance(metadata, dict)
    if mismatch == "execution":
        arguments[1] = "another-execution"
    elif mismatch == "identity":
        metadata["event"]["identity"]["source_generation"] += 1
    elif mismatch == "version":
        metadata["workflow_context"]["execution"]["workflow_version_id"] = "another-version"
    elif mismatch == "principal":
        metadata["event"]["execution_principal_id"] = "not-a-principal-id"
    elif mismatch == "event_type":
        metadata["event"] = None
    elif mismatch == "context_type":
        metadata["workflow_context"] = None
    elif mismatch == "coordinates_type":
        metadata["workflow_context"]["workflow"] = None
    else:
        envelope = arguments[3]
        assert isinstance(envelope, dict)
        envelope["metadata"]["offset"] = "999"
    started = context.event.workflow_execution_started_event_attributes
    started.input.CopyFrom(Payloads(payloads=DataConverter.default.payload_converter.to_payloads(arguments)))
    started.header.CopyFrom(
        Header(
            fields=workflow_auth.build_auth_header(
                context.prepared.temporal_workflow_id, "orchestrator_workflow", arguments
            )
        )
    )
    with pytest.raises(EventLaunchError) as captured:
        await context.launcher.lookup(context.prepared.identity)
    assert captured.value.code == SchedulingFailureCode.EVIDENCE_MISMATCH
    context.client.start_workflow.assert_not_awaited()


async def test_missing_history_after_describe_is_not_absence(launcher_context) -> None:
    context = launcher_context

    history = MagicMock()
    history.__anext__ = AsyncMock(side_effect=RPCError("PRIVATE", RPCStatusCode.NOT_FOUND, b""))
    context.handle.fetch_history_events.side_effect = None
    context.handle.fetch_history_events.return_value = history
    with pytest.raises(EventLaunchError) as captured:
        await context.launcher.lookup(context.prepared.identity)
    assert captured.value.code == SchedulingFailureCode.HISTORY_UNAVAILABLE
    context.client.start_workflow.assert_not_awaited()


@pytest.mark.parametrize("operation", ["describe", "duplicate"])
async def test_queue_configuration_change_preserves_accepted_recovery(launcher_context, operation) -> None:
    context = launcher_context
    # The accepted run and signed history belong to the old queue. A replacement
    # service must recover them using frozen evidence after deployment changes.
    replacement = TemporalWorkflowLauncher(
        TemporalExecutionService(context.client, "replacement-user", background_task_queue="replacement-builtin")
    )
    if operation == "duplicate":
        context.client.start_workflow.side_effect = WorkflowAlreadyStartedError(
            context.prepared.temporal_workflow_id, "orchestrator_workflow", run_id="accepted-run"
        )
        accepted = await replacement.start(context.prepared)
        assert context.client.start_workflow.call_args.kwargs["task_queue"] == "replacement-user"
    else:
        accepted = await replacement._describe(context.prepared, None)
        context.client.start_workflow.assert_not_awaited()
    assert accepted.temporal_run_id == "accepted-run"
    assert context.description.task_queue == "user"
    context.handle.fetch_history_events.assert_called_once()
    context.handle.cancel.assert_not_called()


@pytest.mark.parametrize("mismatch", ["id", "type", "run", "input", "signature", "event"])
async def test_mismatching_evidence_never_resolves(launcher_context, mismatch) -> None:
    context = launcher_context
    prepared = context.prepared
    if mismatch == "id":
        context.description.id = "another-workflow"
    elif mismatch == "type":
        context.description.workflow_type = "another-type"
    elif mismatch == "run":
        context.description.run_id = "other"
    elif mismatch == "input":
        context.event.workflow_execution_started_event_attributes.input.CopyFrom(
            Payloads(payloads=DataConverter.default.payload_converter.to_payloads(["different arguments"]))
        )
    elif mismatch == "signature":
        context.event.workflow_execution_started_event_attributes.header.fields[workflow_auth.HEADER_NAME].data = b"bad"
    else:
        context.event.event_id = 2
    with pytest.raises(EventLaunchError) as captured:
        await context.launcher._describe(prepared, "accepted-run")
    assert captured.value.code == SchedulingFailureCode.EVIDENCE_MISMATCH
    assert not captured.value.transient
    context.client.start_workflow.assert_not_awaited()


@pytest.mark.parametrize(
    "status", [RPCStatusCode.NOT_FOUND, RPCStatusCode.DEADLINE_EXCEEDED, RPCStatusCode.UNAVAILABLE]
)
async def test_describe_failure_is_sanitized_and_never_starts(launcher_context, status) -> None:
    context = launcher_context
    context.handle.describe.side_effect = RPCError("PRIVATE", status, b"")
    with pytest.raises(EventLaunchError) as captured:
        await context.launcher._describe(context.prepared, None)
    assert "PRIVATE" not in str(captured.value)
    expected = (
        SchedulingFailureCode.TEMPORAL_NOT_FOUND
        if status == RPCStatusCode.NOT_FOUND
        else SchedulingFailureCode.TEMPORAL_UNAVAILABLE
    )
    assert captured.value.code == expected
    context.client.start_workflow.assert_not_awaited()
