"""Node-kind permission evaluation helpers (ANSTRAT-1750).

A node-kind check is an ordinary authorization evaluation of
``workflow_node:<action>`` with the node kind carried as the ``kind``
resource label.  These helpers wrap that evaluation for the two places
that need it:

- save time (``write``): the kinds *introduced* by a save compared with
  the latest saved version of the same workflow;
- launch time (``execute``): every executable node of the definition,
  evaluated for the principal the run acts as.

Nothing here touches Rego.  The ``authenticated`` builtin allow grants every
kind by default, so a kind is reported as denied only when a deny policy
matched (or the principal has no effective allow at all).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlmodel import select

from syntara.authz.engine import AuthzRequest, AuthzResult, authorize
from syntara.authz.models.project import Project
from syntara.workflows.node_kinds import (
    NODE_ACTION_EXECUTE,
    NODE_ACTION_WRITE,
    NODE_KIND_LABEL,
    NODE_RESOURCE_TYPE,
    NodeKindCategory,
    get_node_kind,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.evaluator import AuthzEvaluator


@dataclass(frozen=True)
class NodeKindDenial:
    """One node kind the principal may not use for a given action."""

    kind: str
    denied_by: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        """Serialize for API error bodies and execution records."""
        return {"kind": self.kind, "denied_by": self.denied_by, "reason": self.reason}


def kinds_in_definition(definition: dict[str, Any] | None) -> set[str]:
    """Return the set of node kinds (``type`` values) present in a definition dict."""
    if not definition:
        return set()
    nodes = definition.get("nodes") or []
    kinds: set[str] = set()
    for node in nodes:
        if isinstance(node, dict):
            kind = node.get("type")
            if isinstance(kind, str) and kind:
                kinds.add(kind)
    return kinds


def introduced_kinds(new_definition: dict[str, Any] | None, baseline_definition: dict[str, Any] | None) -> set[str]:
    """Kinds present in *new_definition* but absent from *baseline_definition*.

    Presence is the only test: adding a second node of a kind that the
    baseline already contains introduces nothing.  A ``None`` baseline (new
    workflow, clone, import) means every kind is introduced.
    """
    return kinds_in_definition(new_definition) - kinds_in_definition(baseline_definition)


def executable_kinds(kinds: Iterable[str]) -> set[str]:
    """Filter *kinds* down to the ones whose ``execute`` action can be denied.

    Triggers and flow-control kinds are never denied for execution, so they
    are skipped to avoid pointless evaluations.
    """
    result: set[str] = set()
    for kind in kinds:
        info = get_node_kind(kind)
        if info is not None and info.category is NodeKindCategory.ACTION:
            result.add(kind)
    return result


async def resolve_project_name(db: AsyncSession, project_id: UUID | str | None) -> str:
    """Return the project *name* for *project_id* (Rego scopes by name), or ``""``."""
    if project_id is None:
        return ""
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    result = await db.exec(select(Project.name).where(Project.id == pid))
    return result.first() or ""


async def evaluate_node_kinds(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    *,
    user_id: UUID,
    action: str,
    kinds: Iterable[str],
    project_name: str = "",
    user_labels: dict[str, str] | None = None,
    user_metadata: dict[str, Any] | None = None,
) -> dict[str, AuthzResult]:
    """Evaluate ``workflow_node:<action>`` for every kind in *kinds*.

    Args:
        db: Database session used to resolve effective policies.
        evaluator: Authorization evaluator.
        user_id: Principal the check runs as (user or service account id).
        action: ``write`` or ``execute``.
        kinds: Node kinds to evaluate (deduplicated, evaluated in sorted order).
        project_name: Name of the workflow's project (``""`` for none).
        user_labels: Principal labels, when available.
        user_metadata: Principal authz metadata, when available.

    Returns:
        Mapping of kind to its authorization result.

    """
    if action not in (NODE_ACTION_WRITE, NODE_ACTION_EXECUTE):
        msg = f"Unsupported workflow_node action: {action}"
        raise ValueError(msg)
    results: dict[str, AuthzResult] = {}
    for kind in sorted(set(kinds)):
        results[kind] = await authorize(
            db,
            evaluator,
            AuthzRequest(
                user_id=user_id,
                action=action,
                resource_type=NODE_RESOURCE_TYPE,
                resource_id="",
                resource_labels={NODE_KIND_LABEL: kind},
                resource_project=project_name,
                user_labels=user_labels or {},
                user_metadata=user_metadata or {},
            ),
        )
    return results


async def denied_node_kinds(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    *,
    user_id: UUID,
    action: str,
    kinds: Iterable[str],
    project_name: str = "",
    user_labels: dict[str, str] | None = None,
    user_metadata: dict[str, Any] | None = None,
) -> list[NodeKindDenial]:
    """Return the kinds in *kinds* the principal may not use for *action*, sorted by kind."""
    results = await evaluate_node_kinds(
        db,
        evaluator,
        user_id=user_id,
        action=action,
        kinds=kinds,
        project_name=project_name,
        user_labels=user_labels,
        user_metadata=user_metadata,
    )
    return [
        NodeKindDenial(
            kind=kind,
            denied_by=result.denied_by,
            reason=result.denial_reason or ("policy_deny" if result.denied else "no_matching_policy"),
        )
        for kind, result in results.items()
        if not result.allowed
    ]
