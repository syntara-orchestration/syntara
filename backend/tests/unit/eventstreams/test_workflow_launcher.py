"""Temporal adapter policies and signed frozen evidence with isolated RPCs."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from google.protobuf.duration_pb2 import Duration
from temporalio.api.common.v1 import Header, Payloads, WorkflowType
from temporalio.api.history.v1 import HistoryEvent, WorkflowExecutionStartedEventAttributes
from temporalio.api.namespace.v1 import NamespaceConfig
from temporalio.api.workflowservice.v1 import DescribeNamespaceResponse
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
    client.workflow_service.describe_namespace = AsyncMock(
        return_value=DescribeNamespaceResponse(
            config=NamespaceConfig(workflow_execution_retention_ttl=Duration(seconds=259200))
        )
    )
    launcher = TemporalWorkflowLauncher(TemporalExecutionService(client, "user", background_task_queue="builtin"))
    return LauncherContext(prepared, launcher, client, handle, event, description)


@pytest.mark.parametrize(("builtin", "queue"), [(False, "user"), (True, "builtin")])
async def test_start_uses_frozen_arguments_and_explicit_policies(launcher_context, *, builtin, queue) -> None:
    context = launcher_context
    prepared = context.prepared.model_copy(update={"is_builtin": builtin})
    accepted = await context.launcher.start(prepared)
    kwargs = context.client.start_workflow.call_args.kwargs
    assert kwargs["id"] == prepared.claim.identity.temporal_workflow_id
    assert kwargs["args"] == prepared.workflow_arguments()
    assert kwargs["task_queue"] == queue
    assert kwargs["id_reuse_policy"] == WorkflowIDReusePolicy.REJECT_DUPLICATE
    assert kwargs["id_conflict_policy"] == WorkflowIDConflictPolicy.FAIL
    assert accepted.execution_id == prepared.execution_id
    assert accepted.input_fingerprint == prepared.claim.binding.input_fingerprint
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
        accepted = await replacement.describe(context.prepared)
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
        prepared = prepared.model_copy(update={"claim": prepared.claim.model_copy(update={"temporal_run_id": "other"})})
    elif mismatch == "input":
        context.event.workflow_execution_started_event_attributes.input.CopyFrom(
            Payloads(payloads=DataConverter.default.payload_converter.to_payloads(["different arguments"]))
        )
    elif mismatch == "signature":
        context.event.workflow_execution_started_event_attributes.header.fields[workflow_auth.HEADER_NAME].data = b"bad"
    else:
        context.event.event_id = 2
    with pytest.raises(EventLaunchError) as captured:
        await context.launcher.describe(prepared)
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
        await context.launcher.describe(context.prepared)
    assert "PRIVATE" not in str(captured.value)
    expected = (
        SchedulingFailureCode.TEMPORAL_NOT_FOUND
        if status == RPCStatusCode.NOT_FOUND
        else SchedulingFailureCode.TEMPORAL_UNAVAILABLE
    )
    assert captured.value.code == expected
    context.client.start_workflow.assert_not_awaited()


async def test_retention_comes_from_namespace(launcher_context) -> None:
    context = launcher_context
    assert await context.launcher.history_retention_seconds() == 259200
    request = context.client.workflow_service.describe_namespace.call_args.args[0]
    assert request.namespace == "test"


@pytest.mark.parametrize(
    ("status", "transient"),
    [
        (RPCStatusCode.PERMISSION_DENIED, False),
        (RPCStatusCode.UNAUTHENTICATED, False),
        (RPCStatusCode.INVALID_ARGUMENT, False),
        (RPCStatusCode.FAILED_PRECONDITION, False),
        (RPCStatusCode.UNAVAILABLE, True),
        (RPCStatusCode.DEADLINE_EXCEEDED, True),
    ],
)
async def test_namespace_rpc_failure_preserves_classification(launcher_context, status, *, transient) -> None:
    context = launcher_context
    context.client.workflow_service.describe_namespace.side_effect = RPCError("PRIVATE", status, b"")
    with pytest.raises(EventLaunchError) as captured:
        await context.launcher.history_retention_seconds()
    assert captured.value.code == SchedulingFailureCode.HISTORY_UNAVAILABLE
    assert captured.value.transient is transient
    assert "PRIVATE" not in str(captured.value)
    context.client.start_workflow.assert_not_awaited()


async def test_unknown_retention_is_unavailable(launcher_context) -> None:
    context = launcher_context
    context.client.workflow_service.describe_namespace.side_effect = TimeoutError("PRIVATE")
    with pytest.raises(EventLaunchError) as captured:
        await context.launcher.history_retention_seconds()
    assert captured.value.code == SchedulingFailureCode.HISTORY_UNAVAILABLE
    assert captured.value.transient
