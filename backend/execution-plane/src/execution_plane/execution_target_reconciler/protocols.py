"""Query Protocols the reconciler depends on. Persistence stays behind adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from execution_plane.execution_target_reconciler.types import (
        ClusterSnapshot,
        ExecutionTargetSnapshot,
        FilterVerdict,
        IneligibilityReason,
        WorkRequirements,
    )


class ExecutionTargetRegistry(Protocol):
    """Enumerate ExecutionTargets. Each snapshot carries an interned Cluster backref."""

    async def list(self) -> Sequence[ExecutionTargetSnapshot]:
        """Return every ExecutionTarget snapshot."""
        ...


class EligibilityFilter(Protocol):
    """One step in the eligibility chain. A denying verdict stops further filters."""

    name: str

    async def evaluate(
        self,
        cluster: ClusterSnapshot,
        target: ExecutionTargetSnapshot,
        requirements: WorkRequirements,
    ) -> tuple[FilterVerdict, IneligibilityReason | None]:
        """Return ELIGIBLE, or INELIGIBLE with a reason."""
        ...
