"""V2 workflow execution engine with concurrent execution and convergence support.

Parallelism is implicit - when multiple edges originate from the same port (or node),
downstream nodes execute concurrently. No dedicated parallel node type is needed.
"""

import asyncio
import collections
import copy
import json
from datetime import timedelta
from typing import Any, ClassVar, cast

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from syntara.core.exceptions import SafeValueError
    from syntara.workflows.workflow_engine.activities.credential_resolution_activity import resolve_workflow_credentials
    from syntara.workflows.workflow_engine.activities.integration_resolution_activity import (
        resolve_workflow_integration,
    )
    from syntara.workflows.workflow_engine.activities.integration_scope_activity import validate_node_references
    from syntara.workflows.workflow_engine.activities.wait_activity import complete_wait
    from syntara.workflows.workflow_engine.constants import (
        DEFAULT_ACTIVITY_TIMEOUT_SECONDS,
        ENGINE_MAX_OUTPUT_BYTES_KEY,
        ENGINE_TIMEOUT_SECONDS_KEY,
    )
    from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
    from syntara.workflows.workflow_engine.node_settings_resolver import (
        resolve_continue_on_failure,
        resolve_max_iterations,
        resolve_max_output_bytes,
        resolve_retry_policy,
        resolve_timeout,
    )
    from syntara.workflows.workflow_engine.utils.credential_scrubber import scrub_credential_values, scrub_credentials

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.approval_mixin import WorkflowApprovalMixin
from syntara.workflows.workflow_engine.converge_mixin import WorkflowConvergeMixin
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import (
    NODE_OUTPUT_MODELS,
    ConvergeStrategy,
    DoWhileLoopState,
    ForEachLoopState,
    LoopState,
    LoopType,
    NodeType,
)
from syntara.workflows.workflow_engine.unified_eval import safe_eval_with_namespace

# Trigger types allowed for dynamic dispatch via Temporal activities.
# Each entry must have a corresponding @activity.defn with a matching name.
ALLOWED_TRIGGER_TYPES: set[str] = {
    ActivityName.EDA_TRIGGER,
    ActivityName.MANUAL_TRIGGER,
    ActivityName.SCHEDULED_TRIGGER,
    ActivityName.WEBHOOK_TRIGGER,
}

# Marker value for pre-resolved node inputs in test executions
PRE_RESOLVED_MARKER = "__pre_resolved"


def _parse_items(items: Any) -> Any:  # noqa: ANN401
    """Parse loop items from string JSON to a list if needed."""
    if isinstance(items, str):
        try:
            return json.loads(items)
        except (json.JSONDecodeError, ValueError):
            return items
    return items


@workflow.defn(name="orchestrator_workflow")
class NexusWorkflow(WorkflowConvergeMixin, WorkflowApprovalMixin):
    """Temporal workflow for executing v2 graph-based workflows."""

    @workflow.run
    async def run(
        self,
        workflow_definition: dict[str, Any],
        execution_id: str,
        trigger_node_id: str,
        trigger_inputs: dict[str, Any],
        include_node_results: bool = False,  # noqa: FBT001, FBT002
        request_id: str | None = None,
        pre_resolved_outputs: dict[str, dict[str, Any]] | None = None,
        stop_after_nodes: list[str] | None = None,
        workflow_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a v2 workflow with concurrent execution and convergence support.

        Concurrent execution is implicit - when multiple edges originate from the same port,
        downstream nodes execute concurrently.

        Args:
            workflow_definition: Complete v2 workflow definition (triggers + nodes + edges)
            execution_id: Internal execution identifier
            trigger_node_id: ID of the trigger node to execute
            trigger_inputs: User-provided inputs for the trigger
            include_node_results: Whether to include full node results in return value (default: False for production)
            request_id: Optional X-Request-Id (UUID) from the originating HTTP request
            pre_resolved_outputs: Optional dict mapping node IDs to pre-computed outputs for single-node testing
            stop_after_nodes: Optional list of node IDs to stop scheduling successors after execution
            workflow_metadata: Optional dict of workflow/execution metadata for expression resolution

        Returns:
            Workflow execution result matching WorkflowResultResponse schema.
            If include_node_results=True, includes full node results for debugging.

        """
        # Note: Activity monitoring (register_activity_monitoring) should be called
        # by the application code BEFORE starting the workflow execution.
        # This keeps the workflow logic independent of infrastructure concerns.
        try:
            graph = WorkflowGraph.from_dict(workflow_definition)
            self._initialize_state(
                execution_id,
                request_id=request_id,
                pre_resolved_outputs=pre_resolved_outputs,
                stop_after_nodes=stop_after_nodes,
                workflow_metadata=workflow_metadata,
            )
            self._runtime_settings = cast(
                "dict[str, Any]",
                await workflow.execute_local_activity(
                    ActivityName.FETCH_RUNTIME_SETTINGS,
                    activity_id="__internal__fetch_runtime_settings",
                    start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
                ),
            )

            self._build_converge_branch_nodes_index(graph)
            # Scope skips non-trigger nodes; _execute_trigger handles trigger skipping separately.
            self._apply_execution_scope(graph)

            pending_tasks: dict[str, asyncio.Task[Any]] = {}
            await self._execute_trigger(trigger_node_id, trigger_inputs, graph, pending_tasks)
            await self._process_pending_tasks(pending_tasks, graph)
            self._cleanup_timeout_tasks()
            self._mark_remaining_unreachable_nodes(graph)

            return self._build_result(execution_id, include_node_results)

        except asyncio.CancelledError:
            workflow.logger.info("Workflow cancelled, cleaning up pending approvals")
            await self._cancel_approval_requests()
            raise

    def _initialize_state(
        self,
        execution_id: str,
        request_id: str | None = None,
        pre_resolved_outputs: dict[str, dict[str, Any]] | None = None,
        stop_after_nodes: list[str] | None = None,
        workflow_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize all workflow state for a new execution."""
        self.execution_id = execution_id
        self.request_id = request_id
        self.resolver = NamespaceResolver()

        self._project_id: str = ""
        self._created_by_user_id: str = ""
        if workflow_metadata:
            for ns_key, ns_data in workflow_metadata.items():
                self.resolver.set_namespace(ns_key, ns_data)
            wf_ctx = workflow_metadata.get("workflow_context", {})
            self._project_id = wf_ctx.get("workflow", {}).get("project_id", "")
            self._created_by_user_id = wf_ctx.get("execution", {}).get("created_by_user_id", "")

        self.node_inputs: dict[str, dict[str, Any]] = {}
        self.node_control_data: dict[str, dict[str, Any]] = {}
        self.skipped_nodes: set[str] = set()
        self.failed_nodes: dict[str, str] = {}
        self.loop_state: dict[str, LoopState] = {}
        self.loop_body_map: dict[str, str] = {}
        self.loop_iteration_results: dict[str, dict[str, list[Any]]] = {}
        self._timeout_tasks: dict[str, asyncio.Task[Any]] = {}
        self._timed_out_converge_nodes: set[str] = set()
        self._detached_nodes: set[str] = set()
        self._converge_branch_nodes: dict[str, set[str]] = {}
        self._cof_failed_nodes: set[str] = set()
        self._secret_values: set[str] = set()
        self._has_unhandled_failure: bool = False
        self._runtime_settings = {}  # populated by run() after settings fetch
        self.pre_resolved_outputs: dict[str, dict[str, Any]] = pre_resolved_outputs or {}
        self.stop_after_nodes: set[str] = set(stop_after_nodes) if stop_after_nodes else set()

    def _skip_unselected_triggers(self, trigger_node_id: str, graph: WorkflowGraph) -> None:
        """Mark unselected triggers as skipped and propagate to their exclusive downstream nodes."""
        for other_trigger in graph.get_trigger_nodes():
            if other_trigger.id != trigger_node_id:
                self.skipped_nodes.add(other_trigger.id)
                workflow.logger.info(f"Trigger {other_trigger.id} marked as skipped (not selected)")
                self._mark_downstream_as_skipped(other_trigger.id, graph)

    def _apply_execution_scope(self, graph: WorkflowGraph) -> None:
        """Restrict test executions to only ancestor nodes of the target.

        For workflows with parallel branches, this prevents unrelated branches
        from executing when only one branch leads to the target node.
        """
        if not self.stop_after_nodes:
            return
        scope: set[str] = set()
        for target_id in self.stop_after_nodes:
            scope |= self._collect_ancestors(target_id, graph)
        skipped: set[str] = set()
        for node in graph.get_all_nodes():
            if not node.type.endswith("_trigger") and node.id not in scope:
                self.skipped_nodes.add(node.id)
                skipped.add(node.id)
        if skipped:
            workflow.logger.info(f"Nodes skipped (outside execution scope): {skipped}")

    async def _execute_trigger(
        self,
        trigger_node_id: str,
        trigger_inputs: dict[str, Any],
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> None:
        """Execute the trigger node and schedule its successors."""
        trigger_node = graph.get_node(trigger_node_id)
        workflow.logger.info(f"Executing trigger node: {trigger_node.id} (type={trigger_node.type})")

        self._skip_unselected_triggers(trigger_node_id, graph)

        self.node_inputs[trigger_node.id] = trigger_inputs

        # Validate trigger type against allowlist to prevent arbitrary activity dispatch
        if trigger_node.type not in ALLOWED_TRIGGER_TYPES:
            msg = (
                f"Invalid trigger type '{trigger_node.type}'. Allowed types: {', '.join(sorted(ALLOWED_TRIGGER_TYPES))}"
            )
            raise SafeValueError(msg)

        # Dispatch dynamically by trigger type (activity name matches node type for triggers)
        trigger_result = await workflow.execute_activity(
            trigger_node.type,
            args=[trigger_inputs, trigger_node.outputs],
            activity_id=trigger_node.id,
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )

        trigger_output = trigger_result.get("output", trigger_result)
        self.resolver.set_namespace("trigger", trigger_output)
        self.resolver.set_namespace(trigger_node.id, trigger_output)

        await self._schedule_successors(
            completed_node_id=trigger_node.id,
            graph=graph,
            pending_tasks=pending_tasks,
        )

    async def _process_pending_tasks(
        self,
        pending_tasks: dict[str, asyncio.Task[Any]],
        graph: WorkflowGraph,
    ) -> None:
        """Wait for all pending tasks to complete, scheduling successors as they finish."""
        while pending_tasks or self._timed_out_converge_nodes:
            # Cancel pending tasks for nodes that were skipped (by timeout or "any" converge)
            self._cancel_skipped_pending_tasks(pending_tasks)
            self._remove_detached_tasks(pending_tasks)

            # Schedule successors of converge nodes that failed with continue_on_failure
            for node_id in list(self._timed_out_converge_nodes):
                self._timed_out_converge_nodes.discard(node_id)
                workflow.logger.info(f"Scheduling successors of CoF-failed converge node {node_id}")
                await self._schedule_successors(node_id, graph, pending_tasks)

            if not pending_tasks:
                break

            # Include timeout tasks so asyncio.wait wakes up when a timeout fires,
            # rather than blocking until a pending node completes.
            wait_tasks = set(pending_tasks.values())
            for timeout_task in self._timeout_tasks.values():
                if not timeout_task.done():
                    wait_tasks.add(timeout_task)

            done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                completed_node_id = self._find_node_for_task(task, pending_tasks)
                if not completed_node_id:
                    continue

                del pending_tasks[completed_node_id]

                try:
                    output = await task
                except Exception as node_error:  # noqa: BLE001
                    node = graph.get_node(completed_node_id)
                    cof = resolve_continue_on_failure(node, self._runtime_settings)
                    self._handle_node_failure(
                        completed_node_id, node_error, graph, pending_tasks, continue_on_failure=cof
                    )
                    await self._maybe_expire_approval(completed_node_id, node, node_error)
                    if cof:
                        self._route_failed_node(completed_node_id, node)
                        await self._handle_continued_failure(completed_node_id, node, graph, pending_tasks)
                    continue

                self.resolver.set_namespace(completed_node_id, {**output, "status": "completed"})
                workflow.logger.info(f"Node {completed_node_id} completed, pending: {list(pending_tasks.keys())}")

                await self._schedule_successors(
                    completed_node_id=completed_node_id,
                    graph=graph,
                    pending_tasks=pending_tasks,
                )
                self._cancel_skipped_pending_tasks(pending_tasks)

    @staticmethod
    def _find_node_for_task(
        task: asyncio.Task[Any],
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> str | None:
        """Find the node ID associated with a completed task."""
        for nid, t in pending_tasks.items():
            if t == task:
                return nid
        return None

    def _route_failed_node(self, node_id: str, node: ActivityNode) -> None:
        """Set routing for failed nodes so successors follow the correct branch."""
        if node.type == NodeType.LOOP:
            self.node_control_data[node_id] = {"next_port": "complete"}

    def _handle_node_failure(
        self,
        node_id: str,
        error: Exception,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]] | None = None,
        *,
        continue_on_failure: bool = False,
    ) -> None:
        """Record a node failure; skip downstream unless continue_on_failure is set."""
        # Unwrap Temporal's ActivityError to surface the inner ApplicationError message.
        # Also handle bare ApplicationError raised directly from workflow code.
        app_error: ApplicationError | None = None
        if isinstance(error, ActivityError) and isinstance(error.cause, ApplicationError):
            app_error = error.cause
        elif isinstance(error, ApplicationError):
            app_error = error

        error_message = (app_error.message or str(app_error)) if app_error is not None else str(error)

        self.failed_nodes[node_id] = error_message

        # Extract output from ApplicationError.details if executor attached it
        namespace_entry: dict[str, Any] = {}
        if app_error is not None:
            for detail in app_error.details:
                if isinstance(detail, dict) and "output" in detail:
                    namespace_entry = detail["output"]
                    break

        # If no output from executor (e.g. parameters resolution failed), build empty output from model
        if not namespace_entry:
            node = graph.get_node(node_id)
            workflow.logger.debug(f"No output in ApplicationError.details for node {node_id}, using empty model")
            namespace_entry = self._build_empty_node_output(node)

        namespace_entry["status"] = "failed"
        namespace_entry["error"] = error_message

        self.resolver.set_namespace(node_id, namespace_entry)
        workflow.logger.error(f"Node {node_id} failed: {error_message}")
        if not continue_on_failure:
            if node_id not in self._converge_branch_nodes:
                self._has_unhandled_failure = True
            self._mark_downstream_as_skipped(node_id, graph)
        else:
            self._cof_failed_nodes.add(node_id)

        self._check_converge_successors(node_id, graph, pending_tasks)

    @staticmethod
    def _build_empty_node_output(node: ActivityNode) -> dict[str, Any]:
        """Build an empty output dict for a node type using its output model."""
        output_model_class = NODE_OUTPUT_MODELS.get(node.type)
        if output_model_class:
            return output_model_class().dump(node.outputs)
        return {}

    async def _handle_continued_failure(
        self,
        node_id: str,
        node: ActivityNode,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> None:
        """Schedule successors after a node failure when continue_on_failure is true.

        For approval nodes, validates and applies fallback_decision routing before
        scheduling successors. Raises ApplicationError for invalid fallback_decision.
        """
        if node.type == NodeType.APPROVAL:
            resolved = self.node_inputs.get(node_id, node.parameters)
            fallback = resolved.get("fallback_decision", "reject")
            if fallback not in {"approve", "reject"}:
                msg = f"Invalid fallback_decision '{fallback}' on node {node_id}: must be 'approve' or 'reject'"
                raise ApplicationError(msg, type="ConfigError", non_retryable=True)
            port = "approved" if fallback == "approve" else "rejected"
            self.node_control_data[node_id] = {"next_port": port}
        await self._schedule_successors(node_id, graph, pending_tasks)
        self._cancel_skipped_pending_tasks(pending_tasks)

    def _cancel_skipped_pending_tasks(self, pending_tasks: dict[str, asyncio.Task[Any]]) -> None:
        """Cancel pending tasks for nodes that were marked as skipped."""
        skipped_pending = [nid for nid in pending_tasks if nid in self.skipped_nodes]
        for nid in skipped_pending:
            pending_tasks[nid].cancel()
            del pending_tasks[nid]
            workflow.logger.info(f"Cancelled pending task for skipped node {nid}")

    def _detach_in_flight_predecessors(
        self, node_id: str, graph: WorkflowGraph, pending_tasks: dict[str, asyncio.Task[Any]]
    ) -> None:
        """Mark in-flight predecessors as detached when a converge node fails."""
        for pred_id in graph.get_predecessors(node_id):
            if pred_id in pending_tasks and not self.resolver.has_namespace(pred_id):
                self._detached_nodes.add(pred_id)

    def _remove_detached_tasks(self, pending_tasks: dict[str, asyncio.Task[Any]]) -> None:
        """Remove detached in-flight tasks from the main loop without cancelling them.

        When a converge node fails, in-flight predecessors keep running in
        Temporal but no longer block the workflow from completing.
        """
        detached = [nid for nid in pending_tasks if nid in self._detached_nodes]
        for nid in detached:
            del pending_tasks[nid]
            workflow.logger.info(f"Detached in-flight node {nid} from main loop (converge failed)")

    def _cleanup_timeout_tasks(self) -> None:
        """Cancel any remaining converge timeout background tasks."""
        for task in self._timeout_tasks.values():
            task.cancel()
        self._timeout_tasks.clear()

    def _build_result(self, execution_id: str, include_node_results: bool) -> dict[str, Any]:  # noqa: FBT001
        """Build the final workflow execution result."""
        node_outputs = self.resolver.get_all_namespaces()
        # _has_unhandled_failure tracks whether any failure was NOT absorbed by
        # continue_on_failure.  For nodes in a parallel branch the flag is deferred
        # to the converge node: CoF absorbs it, no-CoF sets the flag directly, and
        # a successful converge reconciles any unabsorbed branch failures.  Nodes
        # outside any parallel branch set the flag eagerly on failure.
        if self._has_unhandled_failure:
            workflow_status = "failed"
        elif self.failed_nodes:
            workflow_status = "completed_with_errors"
        else:
            workflow_status = "completed"
        return {
            "status": workflow_status,
            "execution_id": execution_id,
            "activity_outputs": (
                {k: self._scrub_data(v) for k, v in node_outputs.items()} if include_node_results else {}
            ),
            "activity_inputs": (
                {k: self._scrub_data(v) for k, v in self.node_inputs.items()} if include_node_results else {}
            ),
            "completed_activities": list(node_outputs.keys()),
            "failed_activities": self.failed_nodes,
        }

    async def _schedule_successors(
        self,
        completed_node_id: str,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> None:
        """Schedule successor nodes for execution if their dependencies are met.

        For control flow nodes (condition, loop), uses control data to determine
        which output port to follow.

        Args:
            completed_node_id: Node that just completed
            graph: Workflow graph
            pending_tasks: Currently executing tasks

        """
        from_port = self._determine_output_port(completed_node_id)
        completed_node = graph.get_node(completed_node_id)

        # Control-flow nodes must always have routing port data
        if from_port is None and completed_node.type in (
            NodeType.CONDITION,
            NodeType.LOOP,
            NodeType.APPROVAL,
            NodeType.SWITCH,
        ):
            workflow.logger.warning(
                f"Control-flow node {completed_node_id} (type={completed_node.type}) "
                f"has no routing port — returning all successors"
            )

        # Handle branch skipping for control-flow nodes
        if from_port and completed_node.type in (NodeType.CONDITION, NodeType.APPROVAL, NodeType.SWITCH):
            self._skip_non_taken_branches(completed_node_id, from_port, graph)

        # Stop after nodes: return after branch-skipping but before scheduling successors
        if completed_node_id in self.stop_after_nodes:
            return

        successors = graph.get_next_activities_by_port(completed_node_id, from_port)
        is_loop_iterate = completed_node.type == NodeType.LOOP and from_port == "iterate"

        if is_loop_iterate:
            self._setup_loop_namespace(completed_node_id)

        for successor in successors:
            # Track loop body membership (side effect, separate from skip check)
            self._track_loop_body(successor.id, completed_node_id, is_loop_iterate)

            if self._should_skip_successor(successor, completed_node_id, is_loop_iterate, pending_tasks, graph):
                continue

            # Disabled nodes are skipped but their successors still execute
            if getattr(successor.settings, "disabled", None):
                self.skipped_nodes.add(successor.id)
                self.resolver.set_namespace(successor.id, {})
                workflow.logger.info(f"Node {successor.id} is disabled — skipping, scheduling its successors")
                await self._schedule_successors(successor.id, graph, pending_tasks)
                continue

            # All dependencies met — schedule execution
            workflow.logger.info(f"Scheduling node: {successor.id} (type: {successor.type})")
            task = asyncio.create_task(self._execute_node(node=successor, graph=graph))
            pending_tasks[successor.id] = task
            self._handle_converge_timeout(successor.id, graph, pending_tasks)

        # Check if a loop body just completed and needs re-iteration
        self._check_loop_body_completion(completed_node_id, graph, pending_tasks)

    def _skip_non_taken_branches(
        self,
        condition_node_id: str,
        taken_port: str,
        graph: WorkflowGraph,
    ) -> None:
        """Mark successors on non-taken condition branches as skipped."""
        workflow.logger.info(f"Condition node {condition_node_id} routing via port: {taken_port}")
        for edge in graph.get_outgoing_edges(condition_node_id):
            edge_port = edge.get("from_port")
            if edge_port and edge_port != taken_port:
                skipped_successor = edge["to"]
                if skipped_successor not in self.skipped_nodes:
                    self.skipped_nodes.add(skipped_successor)
                    workflow.logger.info(
                        f"Node {skipped_successor} marked as skipped (on non-taken port '{edge_port}')"
                    )
                    self._mark_downstream_as_skipped(skipped_successor, graph)

    def _setup_loop_namespace(self, loop_node_id: str) -> None:
        """Set up the loop namespace with current iteration data."""
        control_data = self.node_control_data.get(loop_node_id, {})
        loop_data: dict[str, Any] = {"index": control_data.get("current_index")}
        if control_data.get("current_item") is not None:
            loop_data["item"] = control_data["current_item"]

        if not self.resolver.has_namespace("loop"):
            self.resolver.set_namespace("loop", {})
        self.resolver.get_namespace("loop")[loop_node_id] = loop_data
        workflow.logger.info(f"Set loop namespace loop.{loop_node_id}: {loop_data}")

    def _track_loop_body(self, successor_id: str, completed_node_id: str, is_loop_iterate: bool) -> None:  # noqa: FBT001
        """Track loop body membership for a successor node."""
        if is_loop_iterate:
            self.loop_body_map[successor_id] = completed_node_id
        elif completed_node_id in self.loop_body_map:
            parent_loop_id = self.loop_body_map[completed_node_id]
            self.loop_body_map[successor_id] = parent_loop_id
            workflow.logger.info(f"Node {successor_id} transitively marked as loop body of {parent_loop_id}")

    def _should_skip_successor(
        self,
        successor: ActivityNode,
        completed_node_id: str,
        is_loop_iterate: bool,  # noqa: FBT001
        pending_tasks: dict[str, asyncio.Task[Any]],
        graph: WorkflowGraph,
    ) -> bool:
        """Check whether a successor should be skipped (not scheduled).

        Side effects: marks remaining predecessors as skipped when an
        'any' converge is satisfied.
        """
        node_id = successor.id

        if (
            node_id in self.skipped_nodes
            or node_id in pending_tasks
            or (
                self.resolver.has_namespace(node_id)
                and not is_loop_iterate
                and completed_node_id not in self.loop_body_map
            )
        ):
            return True

        if successor.type == NodeType.CONVERGE:
            return self._handle_converge_successor(node_id, successor, graph, pending_tasks)

        return False

    def _check_loop_body_completion(
        self,
        completed_node_id: str,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> None:
        """Check if a loop body just completed and the loop should re-iterate."""
        if completed_node_id not in self.loop_body_map:
            return

        parent_loop_id = self.loop_body_map[completed_node_id]
        if self._loop_body_complete(parent_loop_id) and not self._loop_has_pending_nodes(parent_loop_id, pending_tasks):
            self._clear_loop_body(parent_loop_id)
            loop_node = graph.get_node(parent_loop_id)
            workflow.logger.info(f"Re-executing loop node: {parent_loop_id}")
            task = asyncio.create_task(self._execute_node(node=loop_node, graph=graph))
            pending_tasks[parent_loop_id] = task

    def _determine_output_port(self, node_id: str) -> str | None:
        """Determine which output port to follow based on control data.

        Control flow nodes (condition, loop) include routing information in their
        control data. This method extracts the "next_port" field to determine
        which edges to follow.

        Args:
            node_id: Node that just completed

        Returns:
            Port name to follow (e.g., "true", "false", "iterate", "complete"),
            or None for nodes without port-based routing (executor nodes)

        """
        control_data = self.node_control_data.get(node_id)

        if control_data and "next_port" in control_data:
            return str(control_data["next_port"])

        # No control data = no port-based routing (regular executor node)
        return None

    def _are_predecessors_complete(self, node_id: str, graph: WorkflowGraph) -> bool:
        """Check if predecessors of a converge node satisfy its convergence strategy.

        Strategy "all" (default): waits for every predecessor to complete or be skipped.
        Strategy "any": waits for at least ``n_required`` predecessors to complete.

        For conditional branching, skipped predecessors (on non-taken branches)
        are ignored using transitive skip detection.

        Args:
            node_id: Converge node ID to check
            graph: Workflow graph

        Returns:
            True if the convergence condition is satisfied

        """
        predecessor_ids = graph.get_predecessors(node_id)
        node = graph.get_node(node_id)
        strategy = node.parameters.get("strategy", ConvergeStrategy.ALL)
        n_required = node.parameters.get("n_required")

        completed_count = 0

        for pred_id in predecessor_ids:
            if pred_id in self.skipped_nodes:
                continue

            if pred_id in self.failed_nodes:
                if pred_id in self._cof_failed_nodes:
                    completed_count += 1
                continue

            if self.resolver.has_namespace(pred_id):
                completed_count += 1
                continue

            if self._is_unreachable(pred_id, graph):
                self.skipped_nodes.add(pred_id)
                workflow.logger.info(f"Node {pred_id} marked as skipped (transitively unreachable)")
                continue

            # Predecessor is still running (not yet in a terminal state)
            if strategy == ConvergeStrategy.ALL:
                return False

        if strategy == ConvergeStrategy.ANY:
            if n_required is None:
                workflow.logger.error(f"Converge node {node_id} has strategy='any' but no n_required")
                return False
            return completed_count >= int(n_required)

        return True

    def _is_unreachable(self, node_id: str, graph: WorkflowGraph) -> bool:
        """Check if a node is unreachable due to all predecessors being skipped.

        A node is unreachable if every path from it back to a root passes through
        a skipped or failed node. The algorithm does a backwards DFS from node_id.

        A completed predecessor proves reachability only if there is still a
        forward path from it to node_id through non-skipped/non-failed nodes.
        Without that check, a completed node on a different condition branch
        could falsely indicate reachability.

        Args:
            node_id: Node to check
            graph: Workflow graph

        Returns:
            True if node is unreachable (all paths blocked by skipped/failed nodes)

        """
        visited: set[str] = set()
        stack = [node_id]

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)

            if current in self.skipped_nodes or current in self.failed_nodes:
                continue  # This path is blocked, check remaining paths

            # A completed predecessor proves reachability only if it can
            # actually reach node_id through non-blocked edges.  We verify
            # this with a forward has_path check (cheap for nearby nodes).
            if current != node_id and self.resolver.has_namespace(current) and current not in self.failed_nodes:
                if graph.has_forward_path(current, node_id, self.skipped_nodes | set(self.failed_nodes.keys())):
                    return False
                # Completed but no forward path to target — keep searching
                continue

            predecessors = graph.get_predecessors(current)
            if not predecessors:
                # Reached a root node that is not skipped/failed → reachable
                return False

            stack.extend(predecessors)

        # All explored paths lead to skipped/failed nodes → unreachable
        return True

    def _mark_downstream_as_skipped(self, start_node_id: str, graph: WorkflowGraph) -> None:
        """Eagerly mark downstream nodes as skipped via BFS propagation.

        Starting from a skipped node, propagate the skipped status to all
        downstream nodes whose ALL predecessors are already skipped.

        Converge nodes are excluded — their fate is determined by
        ``_check_converge_successors`` / ``_evaluate_converge_failure``
        based on the node's strategy (ALL/ANY).

        Args:
            start_node_id: Node that was just marked as skipped
            graph: Workflow graph

        """
        queue = collections.deque([start_node_id])

        while queue:
            node_id = queue.popleft()

            # Get all immediate successors
            successors = graph.get_successors(node_id)
            for succ_id in successors:
                # Skip if already processed
                if (
                    succ_id in self.skipped_nodes
                    or succ_id in self.failed_nodes
                    or self.resolver.has_namespace(succ_id)
                ):
                    continue

                # Converge nodes have strategy-aware failure logic;
                # let _check_converge_successors handle them.
                succ_node = graph.get_node(succ_id)
                if succ_node.type == NodeType.CONVERGE:
                    continue

                # Check if ALL predecessors of this successor are skipped or failed
                pred_ids = graph.get_predecessors(succ_id)
                all_skipped = all(pred_id in self.skipped_nodes or pred_id in self.failed_nodes for pred_id in pred_ids)

                if all_skipped:
                    self.skipped_nodes.add(succ_id)
                    workflow.logger.info(f"Node {succ_id} marked as skipped (all predecessors skipped)")
                    queue.append(succ_id)  # Propagate further

    def _mark_remaining_unreachable_nodes(self, graph: WorkflowGraph) -> None:
        """Mark any remaining unreachable nodes as skipped.

        After workflow execution completes, any node that wasn't executed
        must be unreachable and should be marked as skipped.

        This catches any nodes that weren't marked during eager propagation due
        to timing (e.g., when branches converge and one branch finishes before
        the other starts).

        Args:
            graph: Workflow graph

        """
        # Get all activity nodes (excluding triggers)
        all_nodes = [node for node in graph.get_all_nodes() if not node.type.endswith("_trigger")]

        for node in all_nodes:
            node_id = node.id

            # Skip if already executed, marked, or detached (still running in Temporal)
            if self.resolver.has_namespace(node_id) or node_id in self.skipped_nodes:
                continue
            if node_id in self._detached_nodes:
                continue

            # If workflow is done and node didn't execute, it's unreachable
            self.skipped_nodes.add(node_id)
            workflow.logger.info(f"Node {node_id} marked as skipped (final pass - unreachable)")

    def _loop_body_complete(self, loop_id: str) -> bool:
        """Check if all loop body nodes have completed.

        For nested loops: a loop node in the body is only considered complete
        if its last routing was to the "complete" port (not "iterate").

        Args:
            loop_id: Loop node ID

        Returns:
            True if all loop body nodes have completed

        """
        # Find all loop body nodes (those mapped to this loop)
        loop_body_nodes = [node_id for node_id, parent in self.loop_body_map.items() if parent == loop_id]

        if not loop_body_nodes:
            # No body nodes tracked — either the body was already cleared for
            # re-iteration (normal), or all body nodes were skipped. In both
            # cases, return False so we don't trigger a spurious re-iteration;
            # _check_loop_body_completion already handles the cleared case.
            return False

        # Check if all have completed
        for node_id in loop_body_nodes:
            if not self.resolver.has_namespace(node_id):
                return False

            # If this body node is itself a loop, check that it finished all iterations
            # (routed to "complete" port on its last execution)
            control_data = self.node_control_data.get(node_id, {})
            if control_data.get("next_port") == "iterate":
                # This loop is still iterating, so the parent loop body is NOT complete
                return False

        return True

    def _loop_has_pending_nodes(self, loop_id: str, pending_tasks: dict[str, asyncio.Task[Any]]) -> bool:
        """Check if any loop body nodes are still pending execution.

        Args:
            loop_id: Loop node ID
            pending_tasks: Currently executing tasks

        Returns:
            True if any loop body nodes are pending

        """
        # Find all loop body nodes
        loop_body_nodes = [node_id for node_id, parent in self.loop_body_map.items() if parent == loop_id]

        return any(node_id in pending_tasks for node_id in loop_body_nodes)

    def _clear_loop_body(self, loop_id: str) -> None:
        """Clear loop body nodes from tracking to allow re-execution.

        Collects iteration results for aggregation. Results remain in resolver
        for query access (sync service), and the last iteration's result persists.

        Args:
            loop_id: Loop node ID

        """
        # Initialize iteration_results for this loop if not exists
        if loop_id not in self.loop_iteration_results:
            self.loop_iteration_results[loop_id] = {}

        # Find all loop body nodes
        loop_body_nodes = [node_id for node_id, parent in self.loop_body_map.items() if parent == loop_id]

        # Collect iteration results for aggregation
        loop_results = self.loop_iteration_results[loop_id]

        for node_id in loop_body_nodes:
            if not self.resolver.has_namespace(node_id):
                continue  # Skip nodes that didn't execute (e.g., skipped by condition)
            node_result = self.resolver.get_namespace(node_id)
            if isinstance(node_result, dict):
                for field_name, field_value in node_result.items():
                    namespaced_key = f"{node_id}.{field_name}"
                    if namespaced_key not in loop_results:
                        loop_results[namespaced_key] = []
                    loop_results[namespaced_key].append(field_value)

        # Clear from loop_body_map to allow fresh tracking on next iteration
        # Results stay in resolver for query access
        for node_id in loop_body_nodes:
            del self.loop_body_map[node_id]

        workflow.logger.info(f"Cleared {len(loop_body_nodes)} loop body nodes from tracking for loop {loop_id}")

    # Seconds added to start_to_close_timeout above the operational deadline so the
    # activity's internal timeout always fires before Temporal cancels the attempt.
    _TEMPORAL_MARGIN: ClassVar[int] = 10

    # Executor node types whose activities enforce their own internal deadline,
    # so Temporal's start_to_close_timeout must include the margin.
    _EXECUTOR_TIMEOUT_MARGIN_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            NodeType.SCRIPT,
            NodeType.HTTP_REQUEST,
            NodeType.INTERNAL_ACTIVITY,
            NodeType.AAP_JOB_TEMPLATE,
            NodeType.AAP_WORKFLOW_JOB_TEMPLATE,
            NodeType.AGENTIC,
        }
    )

    # Mapping from node type to activity name.
    # Approval is NOT in this map — it needs custom args and routing logic.
    _EXECUTOR_ACTIVITY_MAP: ClassVar[dict[str, str]] = {
        NodeType.AAP_JOB_TEMPLATE: ActivityName.AAP_JOB_TEMPLATE,
        NodeType.AAP_WORKFLOW_JOB_TEMPLATE: ActivityName.AAP_WORKFLOW_JOB_TEMPLATE,
        NodeType.HTTP_REQUEST: ActivityName.HTTP_REQUEST,
        NodeType.INTERNAL_ACTIVITY: ActivityName.INTERNAL_ACTIVITY,
        NodeType.SCRIPT: ActivityName.SCRIPT,
        NodeType.CONDITION: ActivityName.CONDITION,
        NodeType.SWITCH: ActivityName.SWITCH,
        NodeType.AGENTIC: ActivityName.AGENTIC,
    }

    async def _execute_executor_node(
        self,
        node: ActivityNode,
        node_type: str,
        resolved_parameters: dict[str, Any],
        outputs: dict[str, str] | None,
        timeout_seconds: int,
        extra_args: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an executor node via the activity map."""
        activity_name = self._EXECUTOR_ACTIVITY_MAP.get(node_type)
        if not activity_name:
            return {"output": {"status": "skipped", "reason": f"Unknown executor type: {node_type}"}}
        args: list[Any] = [resolved_parameters, outputs]
        if extra_args:
            args.extend(extra_args)

        retry_policy = resolve_retry_policy(node, self._runtime_settings)
        return cast(
            "dict[str, Any]",
            await workflow.execute_activity(
                activity_name,
                args=args,
                activity_id=node.id,
                start_to_close_timeout=timedelta(seconds=timeout_seconds),
                retry_policy=retry_policy,
            ),
        )

    async def _execute_wait_node(
        self,
        node_id: str,
        resolved_parameters: dict[str, Any],
        outputs: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Execute a wait node using async completion + durable timer pattern.

        1. Start the wait activity (validates config, raises async completion)
        2. Sleep via workflow.sleep() (durable timer, no worker resources)
        3. Complete the async activity via local activity
        """
        total_seconds = resolved_parameters.get("duration", 0)
        if isinstance(total_seconds, bool) or not isinstance(total_seconds, int) or total_seconds <= 0:
            msg = "Wait duration must be a positive integer (seconds)"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)

        # Step 1: Start wait activity (validates config + global max, calls raise_complete_async)
        wait_handle = workflow.start_activity(
            ActivityName.WAIT,
            args=[resolved_parameters, outputs],
            activity_id=node_id,
            start_to_close_timeout=timedelta(seconds=total_seconds + self._TEMPORAL_MARGIN),
        )

        # Step 2: Durable sleep — survives restarts, no worker resources consumed
        workflow.logger.info(f"Wait node {node_id}: sleeping for {total_seconds}s")
        await workflow.sleep(timedelta(seconds=total_seconds))

        # Step 3: Complete the async wait activity via local activity
        await workflow.execute_local_activity(
            complete_wait,
            args=[workflow.info().workflow_id, workflow.info().run_id, node_id],
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
            activity_id=f"__internal__complete_wait_{node_id}",
        )

        # Await the handle to get the activity result
        result = await wait_handle
        return result if isinstance(result, dict) else {"output": {"status": "completed"}}

    async def _execute_converge_node(
        self,
        node_id: str,
        resolved_parameters: dict[str, Any],
        outputs: dict[str, str] | None,
        graph: WorkflowGraph,
        timeout_seconds: int = DEFAULT_ACTIVITY_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Execute a converge node.

        Args:
            node_id: Node ID
            resolved_parameters: Resolved configuration
            outputs: Output mapping configuration
            graph: Workflow graph
            timeout_seconds: Activity timeout in seconds (default: DEFAULT_ACTIVITY_TIMEOUT_SECONDS)

        Returns:
            Activity result with output and optional control data

        """
        predecessor_ids = graph.get_predecessors(node_id)
        predecessor_results = {}
        for pred_id in predecessor_ids:
            if pred_id not in self.skipped_nodes and self.resolver.has_namespace(pred_id):
                predecessor_results[pred_id] = self.resolver.get_namespace(pred_id)

        # total_branches is injected at runtime (not part of the user-facing parameter schema)
        # so the converge activity can distinguish branch_count from completed_count.
        parameters_with_counts = {**resolved_parameters, "total_branches": len(predecessor_ids)}

        return cast(
            "dict[str, Any]",
            await workflow.execute_activity(
                ActivityName.CONVERGE,
                args=[parameters_with_counts, outputs, predecessor_results],
                activity_id=node_id,
                start_to_close_timeout=timedelta(seconds=timeout_seconds),
            ),
        )

    async def _execute_loop_node(
        self,
        node_id: str,
        node: ActivityNode,
        resolved_parameters: dict[str, Any],
        timeout_seconds: int = DEFAULT_ACTIVITY_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Execute a loop node.

        Args:
            node_id: Node ID
            node: Activity node
            resolved_parameters: Resolved configuration
            timeout_seconds: Activity timeout in seconds (default: DEFAULT_ACTIVITY_TIMEOUT_SECONDS)

        Returns:
            Activity result with output and control data

        """
        loop_type = resolved_parameters.get("type", LoopType.FOR_EACH)

        # Get or initialize loop state
        if node_id not in self.loop_state:
            # Use resolved_parameters for most fields, but keep raw condition template
            # from node.parameters so it can be re-evaluated each iteration.
            loop_init_parameters = {**resolved_parameters, "condition": node.parameters.get("condition")}
            self.loop_state[node_id] = self._create_loop_state_for_type(loop_type, node, loop_init_parameters)

        # Initialize iteration results if not exists
        if node_id not in self.loop_iteration_results:
            self.loop_iteration_results[node_id] = {}

        state = self.loop_state[node_id]

        # For do_while, evaluate condition after first iteration
        condition_result = None
        if isinstance(state, DoWhileLoopState) and state.current_index > 0:
            # Set context for condition evaluation (loop body nodes are available)
            self.resolver.set_context(loop_node_id=node_id)

            # Validate that condition is defined
            if not state.condition:
                msg = f"Loop {node_id} (do_while) has no condition defined"
                raise ValueError(msg)

            # Use unified evaluator (Tier 2) instead of string substitution
            # Wrap in try/finally to guarantee loop context cleanup even if evaluation raises
            try:
                namespace = self.resolver.get_complete_namespace()
                condition_result = safe_eval_with_namespace(state.condition, namespace)
                workflow.logger.info(f"Loop {node_id} condition evaluated: {state.condition} = {condition_result}")
            finally:
                self.resolver.set_context(loop_node_id=None)

        # Pass current state to activity
        loop_parameters: dict[str, Any] = {
            "type": loop_type,
            "current_index": state.current_index,
        }

        max_iter = resolve_max_iterations(node, self._runtime_settings)

        if isinstance(state, ForEachLoopState):
            loop_parameters["items"] = state.items
            condition_result = True
        elif isinstance(state, DoWhileLoopState):
            loop_parameters["condition_result"] = condition_result

        if condition_result is True and state.current_index >= max_iter:
            msg = f"Loop {node_id} exceeded max_iterations ({max_iter})"
            raise ApplicationError(msg, type="MaxIterationsError", non_retryable=True)

        loop_result = cast(
            "dict[str, Any]",
            await workflow.execute_activity(
                ActivityName.LOOP,
                args=[loop_parameters, node.outputs, self.loop_iteration_results[node_id]],
                activity_id=f"{node_id}_iter_{state.current_index}",
                start_to_close_timeout=timedelta(seconds=timeout_seconds),
            ),
        )

        # Update loop state from control data for next iteration
        control_data = loop_result.get("control", {})
        if control_data:
            state.current_index = control_data.get("next_index", 0)

        return loop_result

    def _create_loop_state_for_type(
        self,
        loop_type: str,
        node: ActivityNode,
        loop_parameters: dict[str, Any] | None = None,
    ) -> LoopState:
        """Create appropriate loop state object for the given type.

        All loop parameters are read from loop_parameters for consistency.
        Callers are responsible for ensuring condition contains the raw
        template (not resolved value) when re-evaluation is needed.
        """
        if loop_parameters is None:
            loop_parameters = node.parameters

        if loop_type == LoopType.FOR_EACH:
            items = _parse_items(loop_parameters.get("items", []))
            return ForEachLoopState(items=items)

        condition = loop_parameters.get("condition")
        max_iterations = loop_parameters.get("max_iterations")
        return DoWhileLoopState(condition=condition, max_iterations=max_iterations)

    async def _execute_node(
        self,
        node: ActivityNode,
        graph: WorkflowGraph,
    ) -> dict[str, Any]:
        """Execute a single node: resolve parameters, dispatch, process result.

        Args:
            node: ActivityNode to execute
            graph: Workflow graph

        Returns:
            Node execution result (output portion only, already mapped by activity)

        """
        # Pre-resolved outputs: skip execution and use mocked output
        if node.id in self.pre_resolved_outputs:
            self.node_inputs[node.id] = {PRE_RESOLVED_MARKER: True}

            if node.type == NodeType.LOOP and node.id not in self.loop_state:
                loop_type = node.parameters.get("type", LoopType.FOR_EACH)
                self.loop_state[node.id] = self._create_loop_state_for_type(loop_type, node)
                if node.id not in self.loop_iteration_results:
                    self.loop_iteration_results[node.id] = {}

            return self._process_node_result(node, self.pre_resolved_outputs[node.id])

        node_id = node.id
        node_type = node.type

        # Refresh workflow_context.now and workflow_context.today so each node
        # sees the current wall-clock time, not the execution start time.
        # Uses workflow.now() which is Temporal-safe (deterministic on replay).
        if self.resolver.has_namespace("workflow_context"):
            wf_ctx = self.resolver.get_namespace("workflow_context")
            if isinstance(wf_ctx, dict):
                current_time = workflow.now()
                wf_ctx["now"] = current_time.isoformat()
                wf_ctx["today"] = current_time.strftime("%Y-%m-%d")

        # Special handling for condition nodes (Tier 2)
        if node_type == NodeType.CONDITION:
            # Set loop context if this node is inside a loop body
            self.resolver.set_context(loop_node_id=self.loop_body_map.get(node_id))

            resolved_parameters = {
                "condition": node.parameters.get("condition"),  # Raw template (preserved)
                "namespace": self.resolver.get_complete_namespace(),  # Complete namespace
            }
        elif node_type == NodeType.SWITCH:
            self.resolver.set_context(loop_node_id=self.loop_body_map.get(node_id))

            resolved_parameters = {
                "cases": node.parameters.get("cases", []),
                "default_port": node.parameters.get("default_port", "default"),
                "namespace": self.resolver.get_complete_namespace(),
            }
        else:
            # For all other nodes: standard resolution (Tier 1)
            resolved_parameters = self._resolve_node_parameters(node)

        timeout_seconds = resolve_timeout(node, self._runtime_settings)
        self.node_inputs[node.id] = copy.deepcopy(resolved_parameters)

        result = await self._dispatch_node(node, resolved_parameters, graph, timeout_seconds)
        return self._process_node_result(node, result)

    def _resolve_node_parameters(self, node: ActivityNode) -> dict[str, Any]:
        """Resolve template expressions in a node's parameters.

        Uses two-tier approach:
        - Tier 1 (template substitution): All fields except 'condition'
        - Tier 2 (context-aware): 'condition' field preserved for runtime evaluation

        For condition and loop nodes, the 'condition' field is kept as a raw template
        so it can be evaluated with namespace context at execution time.
        """
        self.resolver.set_context(loop_node_id=self.loop_body_map.get(node.id))

        # For nodes with 'condition' field: preserve it, resolve other fields (Tier 1)
        if node.type in (NodeType.CONDITION, NodeType.LOOP) and "condition" in node.parameters:
            return {
                key: value if key == "condition" else self.resolver.resolve_value(value)
                for key, value in node.parameters.items()
            }

        # For all other nodes: resolve everything (Tier 1)
        return self.resolver.resolve_dict(node.parameters)

    async def _resolve_and_inject_credentials(
        self,
        node: ActivityNode,
        resolved_parameters: dict[str, Any],
    ) -> None:
        """Resolve and inject Nexus credentials for a task node.

        If the node's parameters has a credential_id, calls the credential resolution
        activity to decrypt and inject resolved credentials into the parameters.
        """
        credential_id = resolved_parameters.get("credential_id")
        if not credential_id:
            return

        credential_map = {node.id: credential_id}
        resolved_creds = await workflow.execute_activity(
            resolve_workflow_credentials,
            args=[credential_map, self._project_id],
            activity_id=f"__internal__resolve_credentials_{node.id}",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )

        if node.id in resolved_creds:
            cred_data = resolved_creds[node.id]
            resolved_parameters["_resolved_credentials"] = cred_data
            for val in cred_data.get("_secret_values", []):
                if isinstance(val, str):
                    self._secret_values.add(val)

    _AAP_NODE_TYPES: ClassVar[frozenset[str]] = frozenset(
        {NodeType.AAP_JOB_TEMPLATE, NodeType.AAP_WORKFLOW_JOB_TEMPLATE}
    )

    _REFERENCE_BEARING_NODE_TYPES: ClassVar[frozenset[str]] = frozenset(
        {NodeType.AAP_JOB_TEMPLATE, NodeType.AAP_WORKFLOW_JOB_TEMPLATE, NodeType.AGENTIC}
    )

    async def _validate_node_references(
        self,
        node: ActivityNode,
        resolved_parameters: dict[str, Any],
    ) -> None:
        """Validate integration/model/tool references before dispatch."""
        if node.type not in self._REFERENCE_BEARING_NODE_TYPES:
            return
        ref_keys = (
            "integration_id",
            "integration_connections",
            "llm_model_id",
            "tool_selections",
            "tool_selection_strategy",
        )
        reference_ids = {k: resolved_parameters[k] for k in ref_keys if k in resolved_parameters}
        if not reference_ids:
            return
        await workflow.execute_activity(
            validate_node_references,
            args=[node.type, node.id, reference_ids, self._project_id],
            activity_id=f"__internal__validate_refs_{node.id}",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )

    async def _resolve_and_inject_integration(
        self,
        node: ActivityNode,
        resolved_parameters: dict[str, Any],
    ) -> None:
        """Resolve and inject integration connection settings for AAP nodes.

        If the node has an integration_id, calls the integration resolution
        activity to fetch the integration's URL and SSL settings and injects
        them into the parameters so execution uses the same connection as the UI.
        """
        if node.type not in self._AAP_NODE_TYPES:
            return

        integration_id = resolved_parameters.get("integration_id")
        if not integration_id:
            return

        resolved_integration = await workflow.execute_activity(
            resolve_workflow_integration,
            args=[integration_id],
            activity_id=f"__internal__resolve_integration_{node.id}",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )

        resolved_parameters["_resolved_integration"] = resolved_integration

    @staticmethod
    def _scrub_activity_credentials(resolved_parameters: dict[str, Any]) -> None:
        """Remove resolved credentials and integration data from parameters after execution."""
        resolved_parameters.pop("_resolved_credentials", None)
        resolved_parameters.pop("_resolved_integration", None)
        scrubbed = scrub_credentials(resolved_parameters)
        resolved_parameters.clear()
        resolved_parameters.update(scrubbed)

    async def _dispatch_node(
        self,
        node: ActivityNode,
        resolved_parameters: dict[str, Any],
        graph: WorkflowGraph,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        """Dispatch a node to the appropriate execution handler.

        Validates references, resolves credentials, and scrubs them after execution.
        """
        await self._validate_node_references(node, resolved_parameters)
        await self._resolve_and_inject_credentials(node, resolved_parameters)
        await self._resolve_and_inject_integration(node, resolved_parameters)

        try:
            return await self._dispatch_node_to_executor(node, resolved_parameters, graph, timeout_seconds)
        finally:
            self._scrub_activity_credentials(resolved_parameters)

    async def _dispatch_node_to_executor(
        self,
        node: ActivityNode,
        resolved_parameters: dict[str, Any],
        graph: WorkflowGraph,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        """Route node to the appropriate execution handler."""
        node_id = node.id
        node_type = node.type

        if node_type in self._EXECUTOR_ACTIVITY_MAP:
            extra_args: list[Any] | None = None
            if node_type in self._AAP_NODE_TYPES:
                extra_args = [self.execution_id, self._created_by_user_id]
            elif node_type == NodeType.AGENTIC:
                extra_args = [self.execution_id, self.request_id, self._project_id, self._created_by_user_id]
            # Inject the operational timeout BEFORE adding the Temporal margin so
            # activities use the operator-configured deadline, not the Temporal ceiling.
            parameters_with_timeout = {**resolved_parameters, ENGINE_TIMEOUT_SECONDS_KEY: timeout_seconds}
            if node_type == NodeType.SCRIPT:
                parameters_with_timeout[ENGINE_MAX_OUTPUT_BYTES_KEY] = resolve_max_output_bytes(
                    node, self._runtime_settings
                )
            temporal_timeout = (
                timeout_seconds + self._TEMPORAL_MARGIN
                if node_type in self._EXECUTOR_TIMEOUT_MARGIN_TYPES
                else timeout_seconds
            )
            return await self._execute_executor_node(
                node,
                node_type,
                parameters_with_timeout,
                node.outputs,
                timeout_seconds=temporal_timeout,
                extra_args=extra_args,
            )
        if node_type == NodeType.APPROVAL:
            return await self._execute_approval_node(node, graph, resolved_parameters)
        if node_type == NodeType.WAIT:
            return await self._execute_wait_node(node_id, resolved_parameters, node.outputs)
        if node_type == NodeType.CONVERGE:
            return await self._execute_converge_node(
                node_id, resolved_parameters, node.outputs, graph, timeout_seconds=timeout_seconds
            )
        if node_type == NodeType.LOOP:
            return await self._execute_loop_node(node_id, node, resolved_parameters, timeout_seconds=timeout_seconds)

        return {"output": {"status": "skipped", "reason": f"Unsupported node type: {node_type}"}}

    def _process_node_result(self, node: ActivityNode, result: dict[str, Any]) -> dict[str, Any]:
        """Extract control data and output from an activity result."""
        control_data = result.get("control")
        if control_data:
            self.node_control_data[node.id] = control_data

        output_data = result.get("output", result)

        if isinstance(output_data, dict) and output_data.get("status") == "failed":
            workflow.logger.warning(
                f"Node {node.id} returned status=failed without raising — activity should raise ApplicationError",
                extra={"node_type": node.type},
            )

        workflow.logger.info(
            f"Node {node.id} executed",
            extra={
                "node_type": node.type,
                "has_output_mapping": node.outputs is not None,
                "output_data_keys": list(output_data.keys()) if isinstance(output_data, dict) else "not-a-dict",
            },
        )

        return cast("dict[str, Any]", output_data)

    def _scrub_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Scrub credential keys and secret values from activity data.

        Applies both key-name scrubbing (replaces known credential keys)
        and value-based scrubbing (replaces decrypted secret strings).
        """
        scrubbed = scrub_credentials(data)
        secret_values = getattr(self, "_secret_values", None)
        if secret_values:
            scrubbed = scrub_credential_values(scrubbed, secret_values)
        return cast("dict[str, Any]", scrubbed)

    @workflow.query
    def get_activity_input(self, activity_id: str) -> dict[str, Any] | None:
        """Query to get input data for a specific activity.

        This is consumed by ActivitySyncService to sync activity data to the database.

        Args:
            activity_id: Node ID to get input for

        Returns:
            Activity input data or None if not found

        """
        data = self.node_inputs.get(activity_id)
        if data is None:
            return None
        return self._scrub_data(data)

    @workflow.query
    def get_activity_output(self, activity_id: str) -> dict[str, Any] | None:
        """Query to get output data for a specific activity.

        This is consumed by ActivitySyncService to sync activity data to the database.

        Args:
            activity_id: Node ID to get output for

        Returns:
            Activity output data or None if not found

        """
        data = self.resolver.get_namespace(activity_id) if self.resolver.has_namespace(activity_id) else None
        if data is None:
            return None
        return self._scrub_data(data)

    @workflow.query
    def get_skipped_nodes(self) -> list[str]:
        """Query to get list of skipped node IDs.

        This is consumed by ActivitySyncService to sync skipped status to database.
        Nodes are skipped when they are on non-taken branches of conditional nodes,
        or are transitively unreachable through skipped predecessors.

        Returns:
            List of node IDs that were skipped due to control flow

        """
        return list(self.skipped_nodes)

    @workflow.query
    def get_pre_resolved_nodes(self) -> list[str]:
        """Query to get list of pre-resolved node IDs.

        Pre-resolved nodes had their outputs mocked during test execution
        and were not actually executed.

        Returns:
            List of node IDs that were pre-resolved with mock data

        """
        return list(self.pre_resolved_outputs.keys())

    @workflow.query
    def get_failed_nodes(self) -> dict[str, str]:
        """Query to get failed node IDs and their error messages.

        This is consumed by ActivitySyncService to sync failed status to database.
        Nodes fail when expression resolution or execution raises an exception
        before a Temporal activity is scheduled, so no Temporal event is emitted.

        Returns:
            Dict mapping node ID to error message

        """
        return dict(self.failed_nodes)
