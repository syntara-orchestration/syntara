"""Step-type write-permission evaluation for workflow authoring.

A step-type check is an ordinary authorization evaluation of
``step_type:write`` with the step type carried as the ``kind`` resource
label.  P2 (deny policies for step types) provides the evaluation
helpers and the shared Blocked step type contract consumed by the
save-time 403 (P5) and the node-kinds endpoint (P6).  P5 adds save-time
enforcement on top (executable/introduced label sets).

Nothing here changes the Rego engine: the builtin allow grants a step
type by default, so it is reported as blocked only when a deny policy
matched or the principal has no effective allow at all.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AuthzRequest, AuthzResult, authorize
from syntara.authz.evaluator import AuthzEvaluator
from syntara.workflows.node_kinds import (
    NODE_ACTION_WRITE,
    NODE_KIND_LABEL,
    NODE_RESOURCE_TYPE,
    node_kind_display_label,
)

# A node authorization label set, e.g. {"kind": "script"}.
LabelSet = dict[str, str]


@dataclass(frozen=True)
class NodeKindDenial:
    """A blocked step type (shared contract for P5's 403 and P6's endpoint).

    ``reason`` distinguishes an explicit deny (``explicit_deny``) from the
    absence of a matching allow (``no_matching_allow``).  For an explicit
    deny, ``policy``/``scope``/``project`` come from the matching effective
    statement; for an implicit denial ``policy`` and ``scope`` are ``None``
    and ``project`` is the evaluated project name.  Global denies have
    ``project`` ``None``.
    """

    kind: str
    label: str
    reason: str
    policy: str | None
    scope: str | None
    project: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the shared Blocked step type contract."""
        return {
            "kind": self.kind,
            "label": self.label,
            "reason": self.reason,
            "policy": self.policy,
            "scope": self.scope,
            "project": self.project,
        }


def _deny_targets_step_type_write(entry: dict[str, Any]) -> bool:
    """Return True if *entry* is a deny statement covering step_type:write."""
    return entry.get("effect") == "deny" and f"{NODE_RESOURCE_TYPE}:{NODE_ACTION_WRITE}" in entry.get("actions", [])


def _deny_kind_condition_matches(entry: dict[str, Any], kind: str) -> bool:
    """Return True if *entry*'s resource_labels condition (if any) matches *kind*.

    A deny without a ``resource_labels`` condition covers every kind.
    """
    conditions = entry.get("conditions") or {}
    labels = conditions.get("resource_labels")
    if not isinstance(labels, dict) or NODE_KIND_LABEL not in labels:
        return True
    return bool(labels[NODE_KIND_LABEL] == kind)


def _matching_deny_entry(result: AuthzResult, kind: str, project: str) -> dict[str, Any] | None:
    """Find the effective deny statement the engine attributed the denial to.

    Primary lookup: the entry whose evaluation identifier equals
    ``result.denied_by`` (the deterministic first of the matching deny
    identifiers, as reported by the engine).  Defensive fallback for a
    denied result whose ``denied_by`` does not resolve: the deterministic
    first deny entry targeting step_type:write whose scope matches the
    evaluation and whose kind condition matches.
    """
    if result.denied_by:
        for entry in result.effective_policies:
            if entry.get("name") == result.denied_by and entry.get("effect") == "deny":
                return entry
    candidates = sorted(
        (
            entry
            for entry in result.effective_policies
            if _deny_targets_step_type_write(entry)
            and _deny_kind_condition_matches(entry, kind)
            and (not entry.get("project") or not project or entry.get("project") == project)
        ),
        key=lambda entry: entry.get("name", ""),
    )
    return candidates[0] if candidates else None


def blocked_step_type(result: AuthzResult, kind: str, *, project: str = "") -> NodeKindDenial:
    """Build the Blocked step type contract from an AuthzResult.

    ``allowed`` is ``False`` for both explicit denies and missing allows;
    a result with no resolvable denying statement is reported as
    ``no_matching_allow`` rather than inventing a policy name.

    Raises:
        ValueError: If *result* is allowed — the kind is not blocked.

    """
    if result.allowed:
        msg = f"Step type '{kind}' is allowed; it has no denial to report"
        raise ValueError(msg)
    entry = _matching_deny_entry(result, kind, project)
    if entry is not None:
        is_project_scoped = entry.get("scope") == "project" and bool(entry.get("project"))
        return NodeKindDenial(
            kind=kind,
            label=node_kind_display_label(kind),
            reason="explicit_deny",
            # The originating policy name; the per-statement evaluation
            # identifier ("policyname/1") is never a display name.
            policy=entry.get("policy_name") or entry.get("name"),
            scope="project" if is_project_scoped else None,
            project=entry.get("project") if is_project_scoped else None,
        )
    return NodeKindDenial(
        kind=kind,
        label=node_kind_display_label(kind),
        reason="no_matching_allow",
        policy=None,
        scope=None,
        project=project or None,
    )


async def evaluate_node_labels(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user_id: UUID,
    label_sets: list[LabelSet],
    *,
    project: str = "",
) -> dict[tuple[tuple[str, str], ...], AuthzResult]:
    """Evaluate ``step_type:write`` for every distinct label set.

    Args:
        db: Database session used to resolve effective policies.
        evaluator: Authorization evaluator.
        user_id: Principal the check runs as (user or service account id).
        label_sets: Node label sets to evaluate (deduplicated).
        project: Name of the workflow's project (``""`` for none).

    Returns:
        Mapping of sorted label-set tuple to its authorization result.

    """
    results: dict[tuple[tuple[str, str], ...], AuthzResult] = {}
    for labels in label_sets:
        key = tuple(sorted(labels.items()))
        if key in results:
            continue
        results[key] = await authorize(
            db,
            evaluator,
            AuthzRequest(
                user_id=user_id,
                action=NODE_ACTION_WRITE,
                resource_type=NODE_RESOURCE_TYPE,
                resource_id="",
                resource_labels=dict(labels),
                resource_project=project,
            ),
        )
    return results


async def denied_node_labels(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user_id: UUID,
    label_sets: list[LabelSet],
    *,
    project: str = "",
) -> list[NodeKindDenial]:
    """Return the blocked step types among *label_sets* for the principal.

    ``allowed == False`` counts as blocked regardless of ``denied`` /
    ``denied_by`` — the absence of a matching allow blocks the kind too.
    """
    results = await evaluate_node_labels(db, evaluator, user_id, label_sets, project=project)
    denials: list[NodeKindDenial] = []
    for key, result in results.items():
        kind = dict(key).get(NODE_KIND_LABEL, "")
        if kind and not result.allowed:
            denials.append(blocked_step_type(result, kind, project=project))
    return denials
