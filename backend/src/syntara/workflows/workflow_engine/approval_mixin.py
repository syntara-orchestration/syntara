"""Mixin encapsulating approval node orchestration logic.

Provides approval request creation, decision handling,
timeout expiration, cancellation cleanup, and previous-step context building.
"""

import asyncio
from datetime import timedelta
from typing import Any, ClassVar, cast

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.exceptions import TimeoutError as TemporalTimeoutError

with workflow.unsafe.imports_passed_through():
    from syntara.core.constants import FieldLimits
    from syntara.core.exceptions import SafeValueError
    from syntara.workflows.workflow_engine.activities.approval_activity import fail_detached_approval_activity
    from syntara.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS
    from syntara.workflows.workflow_engine.models.workflow_definition import (
        ActivityName,
        ActivityTerminalStatus,
        ApprovalOutput,
        NodeType,
    )
    from syntara.workflows.workflow_engine.node_settings_resolver import (
        resolve_decision_window,
        resolve_retry_policy,
    )

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
    approval_temporal_activity_id,
    loop_index_chain,
    use_unique_loop_iteration_ids,
)

_APPROVAL_COMMENTS_MAX_LENGTH = FieldLimits.DESCRIPTION_MAX_LENGTH


class WorkflowApprovalMixin:
    """Mixin encapsulating approval node orchestration logic.

    Provides approval request creation, signal-based decision handling,
    timeout expiration, and previous-step context building.

    State attributes are declared as type annotations for mypy;
    initialization remains in ``OrchestratorWorkflow._initialize_state``.
    """

    execution_id: str
    _project_id: str
    resolver: NamespaceResolver
    _runtime_settings: dict[str, Any]
    skipped_nodes: set[str]
    loop_body_map: dict[str, str]
    node_control_data: dict[str, dict[str, Any]]
    _detached_nodes: set[str]
    _TEMPORAL_MARGIN: ClassVar[int]

    def _loop_iteration_path(self, node_id: str) -> list[int]:
        """Return enclosing-loop indices for this node, outermost first (empty if none)."""
        return loop_index_chain(node_id, self.loop_body_map, self.node_control_data)

    def _approval_activity_id(self, node_id: str) -> str:
        """Return the Temporal activity ID for this approval node.

        New executions suffix the canvas ID with the loop-index chain. In-flight
        pre-patch executions keep the canvas ID so replay matches history.
        The Approvals API ``approval_node_id`` is always the canvas ID.
        """
        return approval_temporal_activity_id(node_id, self.loop_body_map, self.node_control_data)

    async def _expire_approvals(self, node_id: str | None, activity_id: str) -> None:
        """Best-effort expire pending approval requests.

        node_id=None expires every pending approval for the execution;
        a specific node_id scopes the expiry to that node only.
        """
        try:
            await workflow.execute_activity(
                ActivityName.EXPIRE_APPROVAL,
                args=[self.execution_id, node_id],
                activity_id=activity_id,
                start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning(
                "Failed to expire approval requests (best-effort): node_id=%s",
                node_id,
            )

    async def _expire_approval_requests(self, node_id: str) -> None:
        """Expire pending approval requests for a timed-out approval node."""
        activity_id = self._approval_activity_id(node_id)
        await self._expire_approvals(node_id, activity_id=f"__internal__expire_approval_{activity_id}")

    async def _maybe_expire_approval(
        self,
        node_id: str,
        node: "ActivityNode",
        error: Exception,
    ) -> None:
        """Expire pending approval requests if an approval node timed out."""
        if (
            node.type == NodeType.APPROVAL
            and isinstance(error, ActivityError)
            and isinstance(error.cause, TemporalTimeoutError)
        ):
            await self._expire_approval_requests(node_id)

    async def _expire_remaining_approvals(self, graph: "WorkflowGraph") -> None:
        """Expire any approvals left pending by a detached approval node.

        Covers approval nodes left pending because a converge/failure path detached
        them before a decision was recorded (e.g. two approval branches where the
        workflow reaches its terminal state after only one is decided). Also fails
        the underlying Temporal activity for each detached approval node so it
        resolves immediately instead of lingering until its own start_to_close_timeout.

        No-ops if nothing was detached: an approval that already resolved via its
        own timeout (``_maybe_expire_approval``) or a normal decision needs no
        further cleanup here.
        """
        detached_approval_ids = [
            node_id for node_id in self._detached_nodes if graph.get_node(node_id).type == NodeType.APPROVAL
        ]
        if not detached_approval_ids:
            return

        await self._expire_approvals(None, activity_id="__internal__expire_remaining_approvals")

        for node_id in detached_approval_ids:
            await self._fail_detached_approval_activity(node_id)

    async def _fail_detached_approval_activity(self, node_id: str) -> None:
        """Best-effort fail the async APPROVAL activity for a single detached node."""
        activity_id = self._approval_activity_id(node_id)
        try:
            await workflow.execute_local_activity(
                fail_detached_approval_activity,
                args=[workflow.info().workflow_id, workflow.info().run_id, activity_id],
                activity_id=f"__internal__fail_detached_approval_{activity_id}",
                start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning(
                "Failed to fail detached approval activity (best-effort): node_id=%s",
                node_id,
            )

    async def _cancel_approval_requests(self) -> None:
        """Best-effort cancel all pending approval requests when workflow is cancelled.

        Uses asyncio.shield to prevent the cleanup activity from being
        cancelled by the already-cancelled workflow scope.
        """
        try:
            await asyncio.shield(
                workflow.execute_activity(
                    ActivityName.CANCEL_APPROVAL,
                    args=[self.execution_id],
                    activity_id="__internal__cancel_approvals",
                    start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning(
                "Failed to cancel approval requests for execution (best-effort)",
            )

    def _get_previous_step_context(
        self,
        node_id: str,
        graph: "WorkflowGraph",
    ) -> dict[str, Any] | None:
        """Build previous_step context for an approval request.

        Finds the predecessor node in the graph and returns its ID, name, type,
        and output for inclusion in the approval's workflow_context.
        """
        predecessors = graph.get_predecessors(node_id)
        if not predecessors:
            return None
        prev_id = predecessors[0]
        prev_node = graph.get_node(prev_id)
        if prev_id in self.skipped_nodes:
            previous_output: dict[str, Any] | None = {"status": "skipped"}
        else:
            try:
                previous_output = self.resolver.get_namespace(prev_id)
            except KeyError:
                previous_output = None
        return {
            "id": prev_node.id,
            "name": prev_node.name or prev_node.id,
            "type": prev_node.type,
            "output": previous_output,
        }

    async def _prepare_approval_args(
        self,
        node: "ActivityNode",
        graph: "WorkflowGraph",
        resolved_parameters: dict[str, Any],
    ) -> list[Any]:
        """Build the positional argument list for create_approval_request_activity.

        New executions return a 12-element list. Pre-patch replay returns the
        original 10-element list so Temporal history matches::

            [0] execution_id:          str            — parent workflow execution ID
            [1] approval_node_id:      str            — canvas node ID
            [2] name:                  str            — display name for the approval request
            [3] next_step_approved:    dict[str, Any] | None — first activity if approved
            [4] workflow_context:      dict[str, Any]  — workflow name, inputs, previous step
            [5] timeout_at:            str | None      — ISO datetime when the request expires
            [6] next_step_rejected:    dict[str, Any] | None — first activity if rejected
            [7] approver_user_ids:     list[str] | None — user UUIDs who can approve
            [8] approver_group_ids:    list[str] | None — group UUIDs whose members can approve
            [9] project_id:            str | None      — project ID for the approval request
            [10] loop_iteration_path:  list[int]       — enclosing-loop indices (empty if none)
            [11] temporal_activity_id: str             — Temporal activity ID actually scheduled

        """
        name = node.name or f"Approval for {node.id}"

        # Build previous step context
        previous_step = self._get_previous_step_context(node.id, graph)

        # Build workflow context
        wf_ctx = (
            self.resolver.get_namespace("workflow_context") if self.resolver.has_namespace("workflow_context") else {}
        )
        execution_ns = wf_ctx.get("execution", {}) if isinstance(wf_ctx, dict) else {}
        workflow_ns = wf_ctx.get("workflow", {}) if isinstance(wf_ctx, dict) else {}
        workflow_context = {
            "workflow_id": workflow_ns.get("id") or execution_ns.get("workflow_version_id", "unknown"),
            "workflow_version": workflow_ns.get("version"),
            "workflow_name": graph.metadata.get("name") or "Unknown",
            "inputs": self.resolver.namespaces.get("trigger", {}),
            "previous_step": previous_step,
        }

        # Build next-step summaries from graph successors by port
        approved_successors = graph.get_next_activities_by_port(node.id, "approved")
        if not approved_successors:
            msg = (
                f"Approval node '{node.id}' has no approved successor. "
                "Approval nodes require at least one successor on the 'approved' output."
            )
            raise SafeValueError(msg)
        first_approved = approved_successors[0]
        next_step_approved = {
            "id": first_approved.id,
            "name": first_approved.name or first_approved.id,
            "type": first_approved.type,
            "parameters": first_approved.parameters,
        }

        rejected_successors = graph.get_next_activities_by_port(node.id, "rejected")
        next_step_rejected = None
        if rejected_successors:
            first_rejected = rejected_successors[0]
            next_step_rejected = {
                "id": first_rejected.id,
                "name": first_rejected.name or first_rejected.id,
                "type": first_rejected.type,
                "parameters": first_rejected.parameters,
            }

        approval_timeout = resolve_decision_window(node, self._runtime_settings)
        timeout_at = (workflow.now() + timedelta(seconds=approval_timeout)).isoformat()

        # Extract approver configuration (string arrays)
        approver_users = resolved_parameters.get("approver_users")
        approver_groups = resolved_parameters.get("approver_groups")

        # Resolve approver usernames/groups to UUIDs (skip if none configured)
        if approver_users or approver_groups:
            approver_resolution = await workflow.execute_activity(
                ActivityName.APPROVER_RESOLUTION,
                args=[approver_users, approver_groups],
                start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
            )
            approver_user_ids = approver_resolution.get("user_ids") or None
            approver_group_ids = approver_resolution.get("group_ids") or None
        else:
            approver_user_ids = None
            approver_group_ids = None

        args = [
            self.execution_id,
            node.id,
            name,
            next_step_approved,
            workflow_context,
            timeout_at,
            next_step_rejected,
            approver_user_ids,
            approver_group_ids,
            self._project_id,
        ]
        # Always call patched() here. Extra args must not appear on replay of
        # histories that scheduled this activity with 10 positional arguments.
        if use_unique_loop_iteration_ids():
            args.extend(
                [
                    self._loop_iteration_path(node.id),
                    self._approval_activity_id(node.id),
                ]
            )
        return args

    async def _execute_approval_node(
        self,
        node: ActivityNode,
        graph: WorkflowGraph,
        resolved_parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an approval node and build the resultSchema output from the signal payload.

        Suspends via Temporal async completion until an external decision is
        received.
        """
        node_id = node.id
        request_id = self._approval_activity_id(node_id)
        approval_args = await self._prepare_approval_args(node, graph, resolved_parameters)
        # Approval uses async completion: start_to_close_timeout must cover the full
        # human decision window, not just the API call to create the request.
        # The margin lets the approval service send its signal right at the deadline
        # without racing our Temporal timeout.
        approval_window = resolve_decision_window(node, self._runtime_settings)
        approval_start_to_close = approval_window + self._TEMPORAL_MARGIN
        retry_policy = resolve_retry_policy(node, self._runtime_settings)
        result = cast(
            "dict[str, Any]",
            await workflow.execute_activity(
                ActivityName.APPROVAL,
                args=approval_args,
                activity_id=request_id,
                start_to_close_timeout=timedelta(seconds=approval_start_to_close),
                retry_policy=retry_policy,
            ),
        )
        raw = result.get("output", {})
        # Pick fields explicitly to match resultSchema; don't pass signal data through blindly.
        decision = raw.get("decision") if isinstance(raw, dict) else None
        approval_output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision=decision,
            decided_by=raw.get("decided_by") if isinstance(raw, dict) else None,
            decided_at=raw.get("decided_at") if isinstance(raw, dict) else None,
            decision_notes=raw["decision_notes"][:_APPROVAL_COMMENTS_MAX_LENGTH]
            if isinstance(raw, dict) and raw.get("decision_notes") is not None
            else None,
        )
        output = approval_output.model_dump(exclude_none=True)
        if decision not in ("approved", "rejected"):
            msg = f"Approval node '{node_id}' received invalid decision '{decision}': expected 'approved' or 'rejected'"
            raise ApplicationError(
                msg,
                {"output": output},
                type="InvalidApprovalDecisionError",
                non_retryable=True,
            )

        workflow.logger.info(
            "Approval node %s decision: %s by %s",
            node_id,
            decision,
            approval_output.decided_by,
        )
        return {"output": output, "control": {"next_port": decision}}
