"""Small helpers for evaluating workflow step types as authorization labels."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import select

from syntara.authz.engine import AuthzRequest, AuthzResult, authorize
from syntara.authz.models.project import Project

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.evaluator import AuthzEvaluator


async def resolve_project_name(db: AsyncSession, project_id: UUID | str | None) -> str:
    """Return the project name used by authorization policy scopes."""
    if project_id is None:
        return ""
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    result = await db.exec(select(Project.name).where(Project.id == pid))
    return result.first() or ""


async def evaluate_node_labels(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    *,
    user_id: UUID,
    action: str,
    label_sets: Iterable[frozenset[tuple[str, str]]],
    project_name: str = "",
    user_labels: dict[str, str] | None = None,
    user_metadata: dict[str, object] | None = None,
) -> dict[frozenset[tuple[str, str]], AuthzResult]:
    """Evaluate one authorization request per distinct step kind."""
    if action != "execute":
        msg = f"Unsupported workflow_node action: {action}"
        raise ValueError(msg)
    results: dict[frozenset[tuple[str, str]], AuthzResult] = {}
    for labels in sorted(set(label_sets), key=lambda item: sorted(item)):
        results[labels] = await authorize(
            db,
            evaluator,
            AuthzRequest(
                user_id=user_id,
                action=action,
                resource_type="workflow_node",
                resource_id="",
                resource_labels=dict(labels),
                resource_project=project_name,
                user_labels=user_labels or {},
                user_metadata=user_metadata or {},
            ),
        )
    return results
