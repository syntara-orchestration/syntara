"""Mixin encapsulating form_prompt node orchestration logic.

Provides form prompt creation, response handling, timeout expiration,
cancellation cleanup, and previous-step context building.
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any, ClassVar, cast

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.exceptions import TimeoutError as TemporalTimeoutError

with workflow.unsafe.imports_passed_through():
    from syntara.core.constants import FieldLimits
    from syntara.core.exceptions import SafeValueError
    from syntara.workflows.workflow_engine.activities.form_prompt_activity import fail_detached_form_prompt_activity
    from syntara.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS
    from syntara.workflows.workflow_engine.models.workflow_definition import (
        ActivityName,
        ActivityTerminalStatus,
        FormPromptOutput,
        NodeType,
    )
    from syntara.workflows.workflow_engine.node_settings_resolver import (
        resolve_form_prompt_response_window,
        resolve_retry_policy,
    )

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
    form_prompt_temporal_activity_id,
    loop_index_chain,
)
from syntara.workflows.workflow_engine.utils.resolved_prompt_text import process_prompt_field

_FORM_PROMPT_MESSAGE_MAX_LENGTH = FieldLimits.DESCRIPTION_MAX_LENGTH


class WorkflowFormPromptMixin:
    """Mixin encapsulating form_prompt node orchestration logic.

    Provides form prompt creation, response-based routing,
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

    # Provided by OrchestratorWorkflow; declared here for mypy only
    _scrub_data: Callable[[dict[str, Any]], dict[str, Any]]

    async def _expire_form_prompts(self, node_id: str | None, activity_id: str) -> None:
        """Best-effort expire pending form prompts.

        node_id=None expires every pending prompt for the execution;
        a specific node_id scopes the expiry to that node only.
        """
        try:
            await workflow.execute_activity(
                ActivityName.EXPIRE_FORM_PROMPT,
                args=[self.execution_id, node_id],
                activity_id=activity_id,
                start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning(
                "Failed to expire form prompts (best-effort): node_id=%s",
                node_id,
            )

    async def _expire_form_prompt_requests(self, node_id: str) -> None:
        """Expire pending form prompts for a timed-out form_prompt node."""
        activity_id = form_prompt_temporal_activity_id(node_id, self.loop_body_map, self.node_control_data)
        await self._expire_form_prompts(node_id, activity_id=f"__internal__expire_form_prompt_{activity_id}")

    async def _maybe_expire_form_prompt(
        self,
        node_id: str,
        node: "ActivityNode",
        error: Exception,
    ) -> None:
        """Expire pending form prompts if a form_prompt node timed out."""
        if (
            node.type == NodeType.FORM_PROMPT
            and isinstance(error, ActivityError)
            and isinstance(error.cause, TemporalTimeoutError)
        ):
            await self._expire_form_prompt_requests(node_id)

    async def _expire_remaining_form_prompts(self, graph: "WorkflowGraph") -> None:
        """Expire all detached form prompts when workflow completes.

        Called when the workflow reaches a terminal state while some form_prompt
        nodes are still pending (e.g., converge with strategy=any where one branch
        completes and the other is abandoned).
        """
        if not self._detached_nodes:
            return

        # Batch expire all pending prompts for this execution
        activity_id = "__internal__expire_remaining_form_prompts"
        await self._expire_form_prompts(node_id=None, activity_id=activity_id)

        # Fail the Temporal activities for each detached node
        for node_id in self._detached_nodes:
            node = graph.get_node(node_id)
            if node.type == NodeType.FORM_PROMPT:
                await self._fail_detached_form_prompt_activity(node_id)

    async def _fail_detached_form_prompt_activity(self, node_id: str) -> None:
        """Fail the async-completion FORM_PROMPT activity for a detached node.

        Resolves the dangling Temporal activity so it doesn't keep waiting forever.
        """
        activity_id = form_prompt_temporal_activity_id(node_id, self.loop_body_map, self.node_control_data)
        try:
            await workflow.execute_local_activity(
                fail_detached_form_prompt_activity,
                args=[workflow.info().workflow_id, workflow.info().run_id, activity_id],
                activity_id=f"__internal__fail_detached_form_prompt_{activity_id}",
                start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning(
                "Failed to fail detached form prompt activity (best-effort): node_id=%s",
                node_id,
            )

    async def _cancel_form_prompts(self) -> None:
        """Cancel all pending form prompts when the workflow is cancelled."""
        try:
            await asyncio.shield(
                workflow.execute_activity(
                    ActivityName.CANCEL_FORM_PROMPT,
                    args=[self.execution_id],
                    activity_id="__internal__cancel_form_prompts",
                    start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning("Failed to cancel form prompts (best-effort)")

    async def _prepare_form_prompt_args(
        self,
        node: "ActivityNode",
        graph: "WorkflowGraph",
        resolved_parameters: dict[str, Any],
    ) -> list[Any]:
        """Build the positional argument list for create_form_prompt_activity.

        Extra args are always appended, never inserted, so Temporal replay of
        older histories still matches. Positional arg contract::

            [0] execution_id:          str
            [1] prompt_node_id:        str
            [2] name:                  str
            [3] form_definition:       dict[str, Any]
            [4] timeout_at:            str | None
            [5] responder_user_ids:    list[str] | None
            [6] responder_group_ids:   list[str] | None
            [7] project_id:            str
            [8] loop_iteration_path:   list[int]
            [9] temporal_activity_id: str
            [10] message:              str | None
            [11] submit_label:         str | None
            [12] success_message:      str | None
            [13] timezone:             str | None
            [14] css_override:         str | None

        """
        # Runtime backstop for the static save-time validator: a form prompt with
        # nothing wired to "submitted" has no destination for a response.
        if not graph.get_next_activities_by_port(node.id, "submitted"):
            msg = (
                f"Form prompt node '{node.id}' has no submitted successor. "
                "Form prompt nodes require at least one successor on the 'submitted' output."
            )
            raise SafeValueError(msg)

        name = node.name or f"Form prompt for {node.id}"

        # Resolve responders (reuse the approver resolution activity - it's generic)
        responder_users = resolved_parameters.get("responder_users") or []
        responder_groups = resolved_parameters.get("responder_groups") or []
        resolution_result = await workflow.execute_activity(
            ActivityName.APPROVER_RESOLUTION,
            args=[responder_users, responder_groups],
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        responder_user_ids = resolution_result.get("user_ids")
        responder_group_ids = resolution_result.get("group_ids")

        # Compute timeout_at
        response_window = resolve_form_prompt_response_window(node, self._runtime_settings)
        timeout_at = (workflow.now() + timedelta(seconds=response_window)).isoformat()

        # Process message field
        message_text = process_prompt_field(
            resolved_parameters,
            field_name="message",
            max_length=_FORM_PROMPT_MESSAGE_MAX_LENGTH,
            scrub_data=self._scrub_data,
        )

        # Get form_definition
        form_definition = resolved_parameters.get("form_definition", {})

        # Get presentation fields
        submit_label = resolved_parameters.get("submit_label")
        success_message = resolved_parameters.get("success_message")
        timezone = resolved_parameters.get("timezone")
        css_override = resolved_parameters.get("css_override")

        # Build positional args in the documented order
        return [
            self.execution_id,
            node.id,
            name,
            form_definition,
            timeout_at,
            responder_user_ids,
            responder_group_ids,
            self._project_id,
            loop_index_chain(node.id, self.loop_body_map, self.node_control_data),
            form_prompt_temporal_activity_id(node.id, self.loop_body_map, self.node_control_data),
            message_text,
            submit_label,
            success_message,
            timezone,
            css_override,
        ]

    async def _execute_form_prompt_node(
        self,
        node: ActivityNode,
        graph: WorkflowGraph,
        resolved_parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a form_prompt node and build the resultSchema output.

        Suspends via Temporal async completion until an external response is
        received or the response window expires.

        On timeout, the ActivityError propagates to the orchestrator which handles
        continue_on_failure routing. If COF is enabled, the orchestrator expires
        the prompt and routes to the "fallback" port.
        """
        node_id = node.id
        prompt_activity_id = form_prompt_temporal_activity_id(node_id, self.loop_body_map, self.node_control_data)
        args = await self._prepare_form_prompt_args(node, graph, resolved_parameters)
        window = resolve_form_prompt_response_window(node, self._runtime_settings)

        result = cast(
            "dict[str, Any]",
            await workflow.execute_activity(
                ActivityName.FORM_PROMPT,
                args=args,
                activity_id=prompt_activity_id,
                start_to_close_timeout=timedelta(seconds=window + self._TEMPORAL_MARGIN),
                retry_policy=resolve_retry_policy(node, self._runtime_settings),
            ),
        )

        # Success path: signal was received
        raw = result.get("output", {})
        outcome = raw.get("outcome") if isinstance(raw, dict) else None

        # Build FormPromptOutput
        response_data = raw.get("response_data")
        responded_by = raw.get("responded_by")
        responded_at = raw.get("responded_at")
        prompt_id = raw.get("prompt_id")

        form_prompt_output = FormPromptOutput(
            status=ActivityTerminalStatus.COMPLETED,
            outcome=outcome,
            response_data=response_data,
            responded_by=responded_by,
            responded_at=responded_at,
            prompt_id=prompt_id,
        )

        output = form_prompt_output.model_dump(exclude_none=True)

        # Determine routing based on outcome
        if outcome == "submitted":
            next_port = "submitted"
        else:
            # Invalid outcome - only "submitted" can arrive via signal
            msg = f"Invalid form prompt outcome: {outcome!r}. Expected 'submitted'."
            raise ApplicationError(msg, {"output": output}, type="InvalidFormPromptOutcomeError", non_retryable=True)

        return {"output": output, "control": {"next_port": next_port}}
