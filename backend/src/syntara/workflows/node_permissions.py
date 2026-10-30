"""Evaluate step authoring permissions and describe blocked step types."""

from collections.abc import Iterable
from typing import Any, Literal
from uuid import UUID

from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AuthzRequest, AuthzResult, authorize
from syntara.authz.evaluator import AuthzEvaluator
from syntara.workflows.node_kinds import NODE_ACTION_WRITE, NODE_KIND_LABEL, NODE_RESOURCE_TYPE, node_kind_label


class NodeKindDenial(SQLModel):
    """Shared blocked-step contract for workflow saves and palette permissions."""

    kind: str
    label: str
    reason: Literal["explicit_deny", "no_matching_allow"]
    policy: str | None
    scope: str | None
    project: str | None


def blocked_step_type(result: AuthzResult, *, kind: str, evaluated_project: str = "") -> NodeKindDenial:
    """Describe a blocked kind using the exact effective statement selected by Rego."""
    if result.allowed:
        msg = "Cannot build a blocked step type from an allowed result"
        raise ValueError(msg)
    if not result.denied:
        return NodeKindDenial(
            kind=kind,
            label=node_kind_label(kind),
            reason="no_matching_allow",
            policy=None,
            scope=None,
            project=evaluated_project or None,
        )
    statement = next(
        (
            entry
            for entry in result.effective_policies
            if entry.get("name") == result.denied_by and entry.get("effect") == "deny"
        ),
        None,
    )
    if statement is None or not statement.get("policy_name"):
        msg = "Explicit step-type deny has no matching effective policy statement"
        raise ValueError(msg)
    return NodeKindDenial(
        kind=kind,
        label=node_kind_label(kind),
        reason="explicit_deny",
        policy=statement["policy_name"],
        scope=statement["scope"],
        project=statement.get("project") if statement["scope"] == "project" else None,
    )


async def evaluate_node_labels(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    *,
    user_id: UUID,
    action: str,
    label_sets: Iterable[frozenset[tuple[str, str]]],
    project_name: str = "",
    user_labels: dict[str, str] | None = None,
    user_metadata: dict[str, Any] | None = None,
) -> dict[frozenset[tuple[str, str]], AuthzResult]:
    """Authorize write once per distinct kind, in a stable order."""
    if action != NODE_ACTION_WRITE:
        msg = f"Unsupported {NODE_RESOURCE_TYPE} action: {action}"
        raise ValueError(msg)
    results: dict[frozenset[tuple[str, str]], AuthzResult] = {}
    for label_set in sorted(set(label_sets), key=sorted):
        results[label_set] = await authorize(
            db,
            evaluator,
            AuthzRequest(
                user_id=user_id,
                action=action,
                resource_type=NODE_RESOURCE_TYPE,
                resource_id="",
                resource_labels=dict(label_set),
                resource_project=project_name,
                user_labels=user_labels or {},
                user_metadata=user_metadata or {},
            ),
        )
    return results


async def denied_node_labels(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    *,
    user_id: UUID,
    action: str,
    label_sets: Iterable[frozenset[tuple[str, str]]],
    project_name: str = "",
    user_labels: dict[str, str] | None = None,
    user_metadata: dict[str, Any] | None = None,
) -> list[NodeKindDenial]:
    """Include both explicit denies and kinds without a matching allow."""
    results = await evaluate_node_labels(
        db,
        evaluator,
        user_id=user_id,
        action=action,
        label_sets=label_sets,
        project_name=project_name,
        user_labels=user_labels,
        user_metadata=user_metadata,
    )
    return [
        blocked_step_type(result, kind=dict(labels)[NODE_KIND_LABEL], evaluated_project=project_name)
        for labels, result in results.items()
        if not result.allowed
    ]
