"""Validate inbound activity callbacks and reconcile Form Prompt outputs.

The generic signal endpoint permits callers with ``execution:run`` to complete
async activities. Form Prompt submission has separate responder and field
validation. A signal can arrive while the Forms API is still creating the
prompt row, so this module classifies the target from the execution's immutable
workflow definition and requires a persisted submission before resuming it.
"""

from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Any, Final, NamedTuple, NoReturn

import structlog

from syntara.forms.services.form_prompt_signal import (
    NotFormPromptSignal,
    RejectedFormPromptSignal,
    resolve_verified_form_prompt_signal,
)
from syntara.workflows.exceptions import FormPromptSubmissionRequiredError
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import candidate_node_ids

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.workflows.models.workflow_definition import WorkflowDefinition

logger = structlog.stdlib.get_logger(__name__)

# signal_data is arbitrary JSON; a tuple keeps non-string statuses safe to compare.
_FAILURE_SIGNAL_STATUSES: Final[tuple[str, ...]] = ("failed", "cancelled")


class CallbackNodeTypeResolution(NamedTuple):
    """Workflow node-type lookup result, including activity-ID collisions."""

    matches: tuple[tuple[str, NodeType], ...]

    @property
    def node_type(self) -> NodeType | None:
        """Return the node type only when exactly one definition matches."""
        return self.matches[0][1] if len(self.matches) == 1 else None

    @property
    def is_ambiguous(self) -> bool:
        """Whether the activity ID matches multiple workflow node definitions."""
        return len(self.matches) > 1

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Return the matching workflow node IDs, sorted by ID."""
        return tuple(node_id for node_id, _ in self.matches)

    @property
    def node_types(self) -> tuple[NodeType, ...]:
        """Return the node types corresponding to ``node_ids``."""
        return tuple(node_type for _, node_type in self.matches)


def _node_identity(node: object) -> tuple[str, str] | None:
    """Return the ID and type from either a trigger dict or workflow-node model."""
    if isinstance(node, dict):
        node_id = node.get("id")
        raw_node_type = node.get("type")
    else:
        node_id = getattr(node, "id", None)
        raw_node_type = getattr(node, "type", None)

    if isinstance(node_id, str) and isinstance(raw_node_type, str):
        return node_id, raw_node_type
    return None


def resolve_callback_node_type(
    workflow_definition: WorkflowDefinition | None,
    activity_id: str,
) -> CallbackNodeTypeResolution:
    """Resolve every exact or loop-base node ID matching a Temporal activity ID.

    Check all progressively shorter loop-ID candidates. Returning the exact
    node ID immediately would miss collisions such as a node named
    ``form_iter_0`` shadowing iteration zero of a Form Prompt named ``form``.
    """
    if workflow_definition is None:
        return CallbackNodeTypeResolution(())

    candidate_ids = set(candidate_node_ids(activity_id))
    matches: dict[str, NodeType] = {}
    # Include triggers too: a trigger ID can collide with a generated node ID.
    for node in chain(workflow_definition.triggers, workflow_definition.nodes):
        identity = _node_identity(node)
        if identity is None or identity[0] not in candidate_ids:
            continue

        node_id, raw_node_type = identity
        try:
            matches[node_id] = NodeType(raw_node_type)
        except ValueError:
            continue

    return CallbackNodeTypeResolution(tuple(sorted(matches.items())))


def _reject_form_prompt_callback(
    event: str,
    *,
    execution_id: UUID,
    activity_id: str,
    acting_user_id: UUID,
    reason: str | None = None,
    **extra: object,
) -> NoReturn:
    """Log and reject a Form Prompt callback while preserving event-specific fields.

    ``reason`` is optional because the ambiguous-target log uses matching node
    details instead of a rejection reason.
    """
    log_context: dict[str, Any] = {
        "execution_id": execution_id,
        "activity_id": activity_id,
        "acting_user_id": acting_user_id,
    }
    if reason is not None:
        log_context["reason"] = reason
    log_context.update(extra)
    logger.warning(event, **log_context)
    raise FormPromptSubmissionRequiredError


async def resolve_form_prompt_callback_payload(
    session: AsyncSession,
    execution_id: UUID,
    activity_id: str,
    workflow_definition: WorkflowDefinition | None,
    status: str | None,
    *,
    acting_user_id: UUID,
) -> dict[str, Any] | None:
    """Return verified Form Prompt output, or None when the callback is generic.

    The workflow definition is committed before execution starts, while the
    Forms API prompt row is created later by an activity. The definition lets
    us recognize a Form Prompt even if its row has not committed yet.
    """
    node_type_resolution = resolve_callback_node_type(workflow_definition, activity_id)
    callback_node_type = node_type_resolution.node_type
    if callback_node_type is not None and callback_node_type != NodeType.FORM_PROMPT:
        # Known non-Form-Prompt activities need no lookup in the Forms table.
        return None

    # Unresolved/legacy IDs still get checked in case a prompt row identifies them.
    if node_type_resolution.is_ambiguous and NodeType.FORM_PROMPT in node_type_resolution.node_types:
        _reject_form_prompt_callback(
            "Rejected Form Prompt signal with ambiguous workflow node ID",
            execution_id=execution_id,
            activity_id=activity_id,
            acting_user_id=acting_user_id,
            matching_node_ids=node_type_resolution.node_ids,
            matching_node_types=[node_type.value for node_type in node_type_resolution.node_types],
        )

    # For a known Form Prompt, absence means its creation is not committed yet;
    # reject instead of falling through to the caller-controlled generic payload.
    resolution = await resolve_verified_form_prompt_signal(
        session,
        execution_id,
        activity_id,
        require_match=callback_node_type == NodeType.FORM_PROMPT,
    )
    if isinstance(resolution, NotFormPromptSignal):
        return None
    if isinstance(resolution, RejectedFormPromptSignal):
        _reject_form_prompt_callback(
            "Rejected Form Prompt activity signal",
            execution_id=execution_id,
            activity_id=activity_id,
            acting_user_id=acting_user_id,
            reason=resolution.reason,
        )
    if status in _FAILURE_SIGNAL_STATUSES:
        _reject_form_prompt_callback(
            "Rejected Form Prompt activity signal",
            execution_id=execution_id,
            activity_id=activity_id,
            acting_user_id=acting_user_id,
            reason="Form Prompt callbacks cannot fail or cancel the activity",
        )
    return resolution.payload
