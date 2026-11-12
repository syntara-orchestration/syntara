"""Finite signed Temporal handoff over detached workflow arguments."""

import asyncio
from datetime import timedelta

from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.constants import EventSchedulingDefaults
from syntara.eventstreams.core.deduplication import DeliveryIdentity, TemporalAcceptance, input_fingerprint
from syntara.eventstreams.core.handler import EventLaunchError, SchedulingFailureCode
from syntara.eventstreams.core.preparation import AcceptedWorkflow, PreparedExecution
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from syntara.workflows.workflow_engine.workflow_auth import HEADER_NAME, verify_workflow

_WORKFLOW_TYPE = "orchestrator_workflow"


def _rpc_failure(exc: RPCError) -> EventLaunchError:
    if exc.status == RPCStatusCode.NOT_FOUND:
        return EventLaunchError(SchedulingFailureCode.TEMPORAL_NOT_FOUND)
    transient = exc.status not in {
        RPCStatusCode.INVALID_ARGUMENT,
        RPCStatusCode.PERMISSION_DENIED,
        RPCStatusCode.UNAUTHENTICATED,
        RPCStatusCode.FAILED_PRECONDITION,
    }
    return EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE, transient=transient)


class TemporalWorkflowLauncher:
    """Reuse the signed client/queue factory; own no database or broker state."""

    def __init__(self, service: TemporalExecutionService) -> None:
        """Receive the existing signed/TLS service from dependency composition."""
        self._service = service
        self._client = service.temporal_client
        self._timeout = timedelta(seconds=EventSchedulingDefaults.RPC_TIMEOUT_SECONDS)

    def _queue(self, prepared: PreparedExecution) -> str:
        return self._service.background_task_queue if prepared.is_builtin else self._service.task_queue

    @staticmethod
    def _acceptance(prepared: PreparedExecution, run_id: str | None) -> TemporalAcceptance:
        binding = prepared.binding
        if (
            not run_id
            or prepared.execution_id != prepared.identity.execution_id
            or prepared.temporal_workflow_id != prepared.identity.temporal_workflow_id
            or prepared.workflow_version_id != binding.workflow_version_id
            or input_fingerprint(prepared.input_data, prepared.workflow_metadata) != binding.input_fingerprint
        ):
            raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
        return TemporalAcceptance(
            execution_id=prepared.execution_id,
            temporal_workflow_id=prepared.temporal_workflow_id,
            temporal_run_id=run_id,
            input_fingerprint=binding.input_fingerprint,
        )

    async def start(self, prepared: PreparedExecution) -> TemporalAcceptance:
        """Submit the identical frozen start; duplicate responses require verification."""
        # Validate references before submitting, even when an adapter is called directly.
        self._acceptance(prepared, "validation")
        try:
            async with asyncio.timeout(self._timeout.total_seconds()):
                handle = await self._client.start_workflow(
                    OrchestratorWorkflow.run,
                    args=prepared.workflow_arguments(),
                    id=prepared.temporal_workflow_id,
                    task_queue=self._queue(prepared),
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                    rpc_timeout=self._timeout,
                )
            return self._acceptance(prepared, handle.first_execution_run_id)
        except WorkflowAlreadyStartedError as exc:
            if exc.workflow_id != prepared.temporal_workflow_id or exc.workflow_type != _WORKFLOW_TYPE:
                raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False) from None
            return await self._describe(prepared, exc.run_id)
        except RPCError as exc:
            raise _rpc_failure(exc) from None
        except (TimeoutError, OSError):
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE) from None

    async def _describe(self, prepared: PreparedExecution, run_id: str | None) -> TemporalAcceptance:
        accepted = await self.lookup(prepared.identity, run_id=run_id)
        if list(accepted.arguments) != prepared.workflow_arguments():
            raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
        return self._acceptance(prepared, accepted.temporal_run_id)

    async def lookup(self, identity: DeliveryIdentity, *, run_id: str | None = None) -> AcceptedWorkflow:
        """Verify retained signed history without needing a newly prepared Execution."""
        described = False
        try:
            async with asyncio.timeout(self._timeout.total_seconds()):
                handle = self._client.get_workflow_handle(identity.temporal_workflow_id, run_id=run_id)
                description = await handle.describe(rpc_timeout=self._timeout)
                described = True
                if (
                    description.id != identity.temporal_workflow_id
                    or description.workflow_type != _WORKFLOW_TYPE
                    or not description.run_id
                    or (run_id is not None and description.run_id != run_id)
                ):
                    raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
                # Pin history to the described run, never to a mutable latest-run handle.
                pinned = self._client.get_workflow_handle(identity.temporal_workflow_id, run_id=description.run_id)
                events = pinned.fetch_history_events(page_size=1, skip_archival=True, rpc_timeout=self._timeout)
                first = await anext(events)
                if first.event_id != 1 or not first.HasField("workflow_execution_started_event_attributes"):
                    raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
                started = first.workflow_execution_started_event_attributes
                arguments = await self._client.data_converter.decode(started.input.payloads)
                token = started.header.fields.get(HEADER_NAME)
                if (
                    started.workflow_type.name != _WORKFLOW_TYPE
                    or token is None
                    or not verify_workflow(identity.temporal_workflow_id, _WORKFLOW_TYPE, arguments, token.data)
                ):
                    raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
                return AcceptedWorkflow.model_validate(
                    {"identity": identity, "temporal_run_id": description.run_id, "arguments": tuple(arguments)},
                    strict=True,
                )
        except RPCError as exc:
            # A described run with unavailable history is not proof of absence.
            if described and exc.status == RPCStatusCode.NOT_FOUND:
                raise EventLaunchError(SchedulingFailureCode.HISTORY_UNAVAILABLE) from None
            raise _rpc_failure(exc) from None
        except (TimeoutError, OSError, StopAsyncIteration):
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE) from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False) from None
