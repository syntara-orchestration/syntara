"""Snapshot DTOs and result types for ExecutionTarget reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from execution_plane.models.cluster import ClusterType
    from execution_plane.models.execution_target import BackendType

ACTIVE_LIFECYCLE = "active"


class ResolveOutcome(StrEnum):
    """Whether at least one ExecutionTarget is eligible."""

    MATCHED = "matched"
    NO_MATCHING_TARGETS = "no_matching_targets"


class IneligibilityReason(StrEnum):
    """Why an ExecutionTarget was excluded from the eligible set."""

    LIFECYCLE = "lifecycle"
    DISABLED = "disabled"
    SELECTOR_MISMATCH = "selector_mismatch"
    CAPACITY_EXHAUSTED = "capacity_exhausted"
    HEALTH = "health"
    POLICY = "policy"


class FilterVerdict(StrEnum):
    """Eligibility decision from one filter."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


@dataclass(frozen=True)
class WorkRequirements:
    """Placement constraints for a work item. Empty selectors take default routing."""

    selectors: dict[str, str] = field(default_factory=dict)
    workload_type: str | None = None


@dataclass(frozen=True)
class ClusterSnapshot:
    """Registered Cluster as seen by the reconciler."""

    id: uuid.UUID
    name: str
    labels: dict[str, str]
    cluster_type: ClusterType
    enabled: bool


@dataclass(frozen=True)
class ExecutionTargetSnapshot:
    """ExecutionTarget plus its Cluster backref. `is_default` drives default routing."""

    id: uuid.UUID
    cluster: ClusterSnapshot
    name: str
    namespace: str
    backend_type: BackendType
    labels: dict[str, str]
    lifecycle: str
    enabled: bool
    is_default: bool = False


@dataclass(frozen=True)
class IneligibleTarget:
    """An ExecutionTarget that failed a filter, with the denying reason."""

    target: ExecutionTargetSnapshot
    reason: IneligibilityReason


@dataclass(frozen=True)
class ReconcileResult:
    """Unordered eligible set plus why other targets were rejected."""

    available_targets: list[ExecutionTargetSnapshot]
    ineligible_targets: list[IneligibleTarget]
    outcome: ResolveOutcome
