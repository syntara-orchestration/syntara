"""Built-in eligibility filters. Health and Policy are no-op pass-throughs until later stories."""

from __future__ import annotations

from typing import TYPE_CHECKING

from execution_plane.execution_target_reconciler.matching import effective_labels, matches_selectors
from execution_plane.execution_target_reconciler.types import (
    ACTIVE_LIFECYCLE,
    FilterVerdict,
    IneligibilityReason,
)

if TYPE_CHECKING:
    from execution_plane.execution_target_reconciler.types import (
        ClusterSnapshot,
        ExecutionTargetSnapshot,
        WorkRequirements,
    )


class LifecycleFilter:
    """Eligible only when the ExecutionTarget is active and enabled."""

    name = "lifecycle"

    async def evaluate(
        self,
        cluster: ClusterSnapshot,
        target: ExecutionTargetSnapshot,
        requirements: WorkRequirements,
    ) -> tuple[FilterVerdict, IneligibilityReason | None]:
        """Deny disabled or non-active targets. Cluster disable is handled by the reconciler."""
        del cluster, requirements
        if not target.enabled:
            return FilterVerdict.INELIGIBLE, IneligibilityReason.DISABLED
        if target.lifecycle != ACTIVE_LIFECYCLE:
            return FilterVerdict.INELIGIBLE, IneligibilityReason.LIFECYCLE
        return FilterVerdict.ELIGIBLE, None


class SelectorFilter:
    """Exact AND match of work selectors against the target's effective labels."""

    name = "selector"

    async def evaluate(
        self,
        cluster: ClusterSnapshot,
        target: ExecutionTargetSnapshot,
        requirements: WorkRequirements,
    ) -> tuple[FilterVerdict, IneligibilityReason | None]:
        """Deny when any requested key is missing or has a different value."""
        labels = effective_labels(cluster, target)
        if matches_selectors(labels, requirements.selectors):
            return FilterVerdict.ELIGIBLE, None
        return FilterVerdict.INELIGIBLE, IneligibilityReason.SELECTOR_MISMATCH


class HealthFilter:
    """Reserved for the Resource Monitor (AAP-92724). Pass-through in MVP."""

    name = "health"

    async def evaluate(
        self,
        cluster: ClusterSnapshot,
        target: ExecutionTargetSnapshot,
        requirements: WorkRequirements,
    ) -> tuple[FilterVerdict, IneligibilityReason | None]:
        """Return eligible until health signals exist."""
        del cluster, target, requirements
        return FilterVerdict.ELIGIBLE, None


class PolicyFilter:
    """Reserved for Isolation Policy (AAP-92726). Pass-through in MVP."""

    name = "policy"

    async def evaluate(
        self,
        cluster: ClusterSnapshot,
        target: ExecutionTargetSnapshot,
        requirements: WorkRequirements,
    ) -> tuple[FilterVerdict, IneligibilityReason | None]:
        """Return eligible until isolation policy exists. Ignore `workload_type`."""
        del cluster, target, requirements
        return FilterVerdict.ELIGIBLE, None


def default_filters() -> tuple[LifecycleFilter, SelectorFilter, HealthFilter, PolicyFilter]:
    """Built-in chain: lifecycle, selector, then no-op health and policy."""
    return (LifecycleFilter(), SelectorFilter(), HealthFilter(), PolicyFilter())
