"""Mixin encapsulating converge node orchestration logic.

Provides convergence gate evaluation, failure cascading,
timeout handling, and incomplete-predecessor skipping.
"""

import asyncio
import collections
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from syntara.workflows.workflow_engine.node_settings_resolver import (
        resolve_continue_on_failure,
        resolve_wait_duration,
    )

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import (
    NODE_OUTPUT_MODELS,
    ConvergeStrategy,
    NodeType,
)


class WorkflowConvergeMixin:
    """Mixin encapsulating converge node orchestration logic.

    Provides convergence gate evaluation, failure cascading,
    timeout handling, and incomplete-predecessor skipping.

    State attributes are declared as type annotations for mypy;
    initialization remains in ``NexusWorkflow._initialize_state``.
    """

    failed_nodes: dict[str, str]
    skipped_nodes: set[str]
    resolver: NamespaceResolver
    _runtime_settings: dict[str, Any]
    _cof_failed_nodes: set[str]
    _has_unhandled_failure: bool
    _timeout_tasks: dict[str, asyncio.Task[Any]]
    _converge_branch_nodes: dict[str, set[str]]
    _timed_out_converge_nodes: set[str]
    _detached_nodes: set[str]

    # Methods provided by NexusWorkflow (resolved via MRO)
    def _are_predecessors_complete(self, node_id: str, graph: WorkflowGraph) -> bool: ...  # type: ignore[empty-body]

    def _mark_downstream_as_skipped(self, start_node_id: str, graph: WorkflowGraph) -> None: ...

    @staticmethod
    def _collect_ancestors(node_id: str, graph: WorkflowGraph) -> set[str]:
        """BFS backward from a node to collect all of its ancestors (inclusive)."""
        ancestors: set[str] = set()
        queue = collections.deque([node_id])
        while queue:
            current = queue.popleft()
            if current in ancestors:
                continue
            ancestors.add(current)
            queue.extend(graph.get_predecessors(current))
        return ancestors

    def _build_converge_branch_nodes_index(self, graph: WorkflowGraph) -> None:
        """Build a reverse index mapping parallel-section nodes to their converge nodes.

        For each converge node the "parallel section" is the set of nodes
        between the fork point and the converge.  The fork is identified by
        intersecting the ancestor sets of each direct predecessor — the common
        ancestors are the fork and everything above it, so the parallel section
        is the union minus the intersection.

        For single-predecessor converge nodes the direct predecessor is used.
        """
        for node in graph.get_all_nodes():
            if node.type != NodeType.CONVERGE:
                continue
            direct_preds = graph.get_predecessors(node.id)
            if len(direct_preds) <= 1:
                for pred_id in direct_preds:
                    self._converge_branch_nodes.setdefault(pred_id, set()).add(node.id)
                continue
            ancestor_sets = [self._collect_ancestors(pid, graph) for pid in direct_preds]
            common = ancestor_sets[0].copy()
            for s in ancestor_sets[1:]:
                common &= s
            parallel_section: set[str] = set()
            for s in ancestor_sets:
                parallel_section |= s - common
            for pred_id in parallel_section:
                self._converge_branch_nodes.setdefault(pred_id, set()).add(node.id)

    def _handle_converge_timeout(
        self,
        scheduled_node_id: str,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> None:
        """Start a converge timeout when a parallel-section node is first scheduled."""
        converge_ids = self._converge_branch_nodes.get(scheduled_node_id)
        if not converge_ids:
            return
        for converge_id in converge_ids:
            if converge_id in self._timeout_tasks:
                continue
            if converge_id in self.failed_nodes or converge_id in self.skipped_nodes:
                continue
            converge_node = graph.get_node(converge_id)
            timeout_seconds = float(resolve_wait_duration(converge_node, self._runtime_settings))
            workflow.logger.info(f"Starting converge timeout for {converge_id}: {timeout_seconds}s")
            self._timeout_tasks[converge_id] = asyncio.create_task(
                self._converge_timeout_handler(converge_id, graph, timeout_seconds, pending_tasks)
            )

    def _check_converge_successors(
        self,
        failed_node_id: str,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]] | None = None,
    ) -> None:
        """Check if any reachable converge node should fail after a node failure.

        Uses BFS through skipped/failed intermediate nodes to find converge
        nodes that are not direct successors of the failed node.
        """
        visited: set[str] = set()
        queue = collections.deque([failed_node_id])

        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            for succ_id in graph.get_successors(current_id):
                if succ_id in visited:
                    continue
                succ_node = graph.get_node(succ_id)

                if succ_node.type == NodeType.CONVERGE:
                    if succ_id in self.failed_nodes or self.resolver.has_namespace(succ_id):
                        continue
                    self._evaluate_converge_failure(
                        succ_id,
                        succ_node,
                        graph,
                        pending_tasks,
                        upstream_failure_id=failed_node_id,
                    )
                elif succ_id in self.skipped_nodes or succ_id in self.failed_nodes:
                    queue.append(succ_id)

    def _evaluate_converge_failure(
        self,
        converge_id: str,
        converge_node: ActivityNode,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]] | None = None,
        *,
        upstream_failure_id: str | None = None,
    ) -> None:
        """Evaluate whether a converge node should fail.

        Args:
            converge_id: ID of the converge node to evaluate.
            converge_node: The converge node object.
            graph: Workflow graph.
            pending_tasks: Currently executing tasks.
            upstream_failure_id: When set, this converge was reached via BFS from
                a failed node through skipped/failed intermediates.  For ALL
                strategy this means a branch is dead and the converge should fail.
                When ``None``, only direct predecessor failures are checked.

        """
        strategy = converge_node.parameters.get("strategy", ConvergeStrategy.ALL)
        predecessor_ids = graph.get_predecessors(converge_id)

        if strategy == ConvergeStrategy.ALL:
            failed_preds = [p for p in predecessor_ids if p in self.failed_nodes and p not in self._cof_failed_nodes]
            if failed_preds:
                error_msg = (
                    f"Converge node {converge_id}: predecessor(s) "
                    f"{', '.join(failed_preds)} failed, "
                    f"ALL strategy requires every branch to succeed"
                )
                self._fail_converge_node(converge_id, error_msg, graph, pending_tasks)
                return

            if upstream_failure_id and upstream_failure_id not in self._cof_failed_nodes:
                error_msg = (
                    f"Converge node {converge_id}: upstream node "
                    f"{upstream_failure_id} failed, "
                    f"ALL strategy requires every branch to succeed"
                )
                self._fail_converge_node(converge_id, error_msg, graph, pending_tasks)
                return

        if self._all_predecessors_terminal(predecessor_ids) and not self._are_predecessors_complete(converge_id, graph):
            n_req = converge_node.parameters.get("n_required", "?")
            successes = self._count_successful_predecessors(predecessor_ids)
            error_msg = (
                f"Converge node {converge_id}: required {n_req} successful branches, "
                f"got {successes} (failures excluded)"
            )
            self._fail_converge_node(converge_id, error_msg, graph, pending_tasks)

    def _all_predecessors_terminal(self, predecessor_ids: list[str]) -> bool:
        """Check if every predecessor has reached a terminal state (completed, failed, or skipped)."""
        return all(
            p in self.skipped_nodes or p in self.failed_nodes or self.resolver.has_namespace(p) for p in predecessor_ids
        )

    def _count_successful_predecessors(self, predecessor_ids: list[str]) -> int:
        """Count predecessors that completed successfully (not failed, not skipped)."""
        return sum(
            1
            for p in predecessor_ids
            if p not in self.skipped_nodes
            and self.resolver.has_namespace(p)
            and (p not in self.failed_nodes or p in self._cof_failed_nodes)
        )

    def _fail_converge_node(
        self,
        node_id: str,
        error_msg: str,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]] | None = None,
    ) -> None:
        """Mark a converge node as failed and clean up.

        Checks ``continue_on_failure`` on the converge node: when true the
        failure is recorded but downstream nodes are scheduled instead of
        skipped (via ``_timed_out_converge_nodes``).
        """
        node = graph.get_node(node_id)
        cof = resolve_continue_on_failure(node, self._runtime_settings)

        self.failed_nodes[node_id] = error_msg
        self.skipped_nodes.discard(node_id)
        output_model_class = NODE_OUTPUT_MODELS.get(node.type)
        fail_output = output_model_class().dump(node.outputs) if output_model_class else {}
        fail_output["status"] = "failed"
        fail_output["error"] = error_msg
        self.resolver.set_namespace(node_id, fail_output)
        if pending_tasks is not None:
            try:
                self._skip_incomplete_predecessors(node_id, graph, "converge failed", pending_tasks)
            except Exception:  # noqa: BLE001
                workflow.logger.exception(f"Failed to skip incomplete predecessors for {node_id}")
            for branch_node_id, converge_ids in self._converge_branch_nodes.items():
                if (
                    node_id in converge_ids
                    and branch_node_id in pending_tasks
                    and not self.resolver.has_namespace(branch_node_id)
                ):
                    self._detached_nodes.add(branch_node_id)
        if cof:
            self._cof_failed_nodes.add(node_id)
            for branch_node_id, converge_ids in self._converge_branch_nodes.items():
                if node_id in converge_ids and branch_node_id in self.failed_nodes:
                    self._cof_failed_nodes.add(branch_node_id)
            self._timed_out_converge_nodes.add(node_id)
        else:
            self._has_unhandled_failure = True
            self._mark_downstream_as_skipped(node_id, graph)
        timeout_task = self._timeout_tasks.pop(node_id, None)
        if timeout_task is not None:
            timeout_task.cancel()
        self._check_converge_successors(node_id, graph, pending_tasks)

    def _handle_converge_successor(
        self,
        node_id: str,
        successor: ActivityNode,
        graph: WorkflowGraph,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> bool:
        """Decide whether a converge successor should be skipped or scheduled.

        Returns True if the converge node should be skipped (not scheduled).
        """
        if node_id in self.failed_nodes:
            return True

        self._evaluate_converge_failure(node_id, successor, graph, pending_tasks)
        if node_id in self.failed_nodes:
            return True

        # Gate not satisfied yet — wait or skip
        if not self._are_predecessors_complete(node_id, graph):
            predecessor_ids = graph.get_predecessors(node_id)
            if self._all_predecessors_terminal(predecessor_ids):
                self.skipped_nodes.add(node_id)
                workflow.logger.info(
                    f"Converge node {node_id} marked as skipped (n_required not met, all branches terminal)"
                )
                self._mark_downstream_as_skipped(node_id, graph)
                return True

            workflow.logger.info(f"Converge node {node_id} waiting for predecessors to complete")
            return True

        # Gate satisfied — for ANY, skip branches that haven't started and detach in-flight ones
        strategy = successor.parameters.get("strategy", ConvergeStrategy.ALL)
        if strategy == ConvergeStrategy.ANY:
            self._skip_incomplete_predecessors(node_id, graph, "n_required met", pending_tasks)
            for branch_node_id, converge_ids in self._converge_branch_nodes.items():
                if (
                    node_id in converge_ids
                    and branch_node_id in pending_tasks
                    and not self.resolver.has_namespace(branch_node_id)
                ):
                    self._detached_nodes.add(branch_node_id)

        return False

    async def _converge_timeout_handler(
        self,
        node_id: str,
        graph: WorkflowGraph,
        timeout_seconds: float,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> None:
        """Background task that waits for converge predecessors or fires a timeout.

        On timeout the converge node is failed via ``_fail_converge_node``.
        Recovery is governed by ``continue_on_failure`` on the node's settings.
        """
        try:
            timed_out = False
            try:
                await workflow.wait_condition(
                    lambda cid=node_id: self._are_predecessors_complete(cid, graph),  # type: ignore[misc]
                    timeout=timedelta(seconds=timeout_seconds),
                )
            except TimeoutError:
                timed_out = True

            if timed_out:
                error_msg = f"Converge node {node_id} timed out after {timeout_seconds}s waiting for predecessors"
                workflow.logger.error(error_msg)
                self._fail_converge_node(node_id, error_msg, graph, pending_tasks)
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Converge timeout handler error for {node_id}: {exc}"
            workflow.logger.error(error_msg)
            self._fail_converge_node(node_id, error_msg, graph, pending_tasks)

    def _skip_incomplete_predecessors(
        self,
        node_id: str,
        graph: WorkflowGraph,
        reason: str,
        pending_tasks: dict[str, asyncio.Task[Any]],
    ) -> None:
        """Mark incomplete predecessors of a converge node as skipped.

        Used both when a converge timeout fires and when an 'any' strategy
        converge node has met its n_required threshold.

        Args:
            node_id: Converge node whose predecessors to check
            graph: Workflow graph
            reason: Human-readable reason for the skip (included in log messages)
            pending_tasks: Currently executing node tasks (in-flight nodes are not skipped)

        """
        newly_skipped = []
        for pred_id in graph.get_predecessors(node_id):
            if pred_id not in self.skipped_nodes and not self.resolver.has_namespace(pred_id):
                if pred_id in pending_tasks:
                    workflow.logger.info(f"Converge: predecessor {pred_id} is still in flight, not skipping")
                    continue
                self.skipped_nodes.add(pred_id)
                newly_skipped.append(pred_id)
                workflow.logger.info(f"Converge: predecessor {pred_id} skipped ({reason})")
        for pred_id in newly_skipped:
            self._mark_downstream_as_skipped(pred_id, graph)
