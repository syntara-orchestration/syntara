"""ExecutionTarget Reconciler — pure query over a flat ExecutionTarget list."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from execution_plane.execution_target_reconciler.filters import SelectorFilter
from execution_plane.execution_target_reconciler.matching import (
    any_cluster_identity_pinned,
    cluster_is_identity_pinned,
    remaining_selectors_after_cluster_affinity,
)
from execution_plane.execution_target_reconciler.types import (
    FilterVerdict,
    IneligibilityReason,
    IneligibleTarget,
    ReconcileResult,
    ResolveOutcome,
    WorkRequirements,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from execution_plane.execution_target_reconciler.protocols import EligibilityFilter, ExecutionTargetRegistry
    from execution_plane.execution_target_reconciler.types import ClusterSnapshot, ExecutionTargetSnapshot

logger = structlog.stdlib.get_logger(__name__)


class ExecutionTargetReconciler:
    """Resolve the unordered set of eligible ExecutionTargets for a work item."""

    def __init__(
        self,
        targets: ExecutionTargetRegistry,
        filters: Sequence[EligibilityFilter],
    ) -> None:
        """Bind the target query Protocol and the eligibility chain."""
        self._targets = targets
        self._filters = tuple(filters)

    async def resolve(self, requirements: WorkRequirements) -> ReconcileResult:
        """Return available and ineligible targets. No-match is an outcome, not an exception."""
        listed = list(await self._targets.list())
        identity_pinned = any_cluster_identity_pinned(
            [target.cluster for target in listed],
            requirements.selectors,
        )
        available: list[ExecutionTargetSnapshot] = []
        ineligible: list[IneligibleTarget] = []

        for target in listed:
            cluster = target.cluster
            if not cluster.enabled:
                continue
            if identity_pinned and not cluster_is_identity_pinned(cluster, requirements.selectors):
                continue
            verdict, reason = await self._evaluate(cluster, target, requirements)
            if verdict is FilterVerdict.ELIGIBLE:
                available.append(target)
            elif reason is not None:
                ineligible.append(IneligibleTarget(target, reason))

        if not requirements.selectors:
            available = _default_routing(available)

        outcome = ResolveOutcome.MATCHED if available else ResolveOutcome.NO_MATCHING_TARGETS
        logger.debug(
            "Reconciled execution targets",
            outcome=outcome.value,
            available=len(available),
            ineligible=len(ineligible),
        )
        return ReconcileResult(available, ineligible, outcome)

    async def _evaluate(
        self,
        cluster: ClusterSnapshot,
        target: ExecutionTargetSnapshot,
        requirements: WorkRequirements,
    ) -> tuple[FilterVerdict, IneligibilityReason | None]:
        """Run the filter chain. SelectorFilter is skipped on the default-routing path."""
        apply_selector = bool(requirements.selectors)
        filter_requirements = requirements
        if apply_selector:
            filter_requirements = WorkRequirements(
                selectors=remaining_selectors_after_cluster_affinity(cluster, requirements.selectors),
                workload_type=requirements.workload_type,
            )
        for filt in self._filters:
            if not apply_selector and isinstance(filt, SelectorFilter):
                continue
            verdict, reason = await filt.evaluate(cluster, target, filter_requirements)
            if verdict is FilterVerdict.INELIGIBLE:
                return verdict, reason
        return FilterVerdict.ELIGIBLE, None


def _default_routing(lifecycle_eligible: list[ExecutionTargetSnapshot]) -> list[ExecutionTargetSnapshot]:
    """Prefer `is_default` targets when any exist; otherwise keep every lifecycle-eligible target."""
    defaults = [target for target in lifecycle_eligible if target.is_default]
    return defaults or lifecycle_eligible
