"""ExecutionTargetReconciler.resolve against the design examples and edge cases."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from execution_plane.execution_target_reconciler.filters import (
    HealthFilter,
    LifecycleFilter,
    PolicyFilter,
    SelectorFilter,
    default_filters,
)
from execution_plane.execution_target_reconciler.reconciler import ExecutionTargetReconciler
from execution_plane.execution_target_reconciler.types import (
    ClusterSnapshot,
    ExecutionTargetSnapshot,
    FilterVerdict,
    IneligibilityReason,
    ReconcileResult,
    ResolveOutcome,
    WorkRequirements,
)
from execution_plane.models.execution_target import BackendType

MakeCluster = Callable[..., ClusterSnapshot]
MakeTarget = Callable[..., ExecutionTargetSnapshot]
MakeReconciler = Callable[[list[ExecutionTargetSnapshot]], ExecutionTargetReconciler]


def _names(result: ReconcileResult) -> set[str]:
    return {target.name for target in result.available_targets}


@pytest.mark.asyncio
async def test_example_00_empty_selectors_select_the_cluster_default(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster(name="local-openshift", labels={"cluster": "local-openshift"})
    default = make_target(cluster, name="ep-default", is_default=True)
    extra = make_target(cluster, name="ep-gpu", labels={"gpu": "true"})
    resolver = make_reconciler([default, extra])

    result = await resolver.resolve(WorkRequirements())

    assert result.outcome is ResolveOutcome.MATCHED
    assert _names(result) == {"ep-default"}


@pytest.mark.asyncio
async def test_example_01_region_and_env_select_the_matching_namespace(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    east = make_cluster(name="ocp-us-east-1", labels={"region": "us-east-1"})
    west = make_cluster(name="ocp-eu-west-1", labels={"region": "eu-west-1"})
    east_default = make_target(east, name="ep-default", is_default=True)
    production = make_target(east, name="ns-production", namespace="production", labels={"env": "production"})
    west_default = make_target(west, name="ep-default-west", is_default=True)
    resolver = make_reconciler([east_default, production, west_default])

    result = await resolver.resolve(WorkRequirements(selectors={"region": "us-east-1", "env": "production"}))

    assert result.outcome is ResolveOutcome.MATCHED
    assert _names(result) == {"ns-production"}
    assert result.available_targets[0].cluster is east


@pytest.mark.asyncio
async def test_example_04_unmatched_region_is_no_matching_targets(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    east = make_cluster(name="ocp-us-east-1", labels={"region": "us-east-1"})
    west = make_cluster(name="ocp-eu-west-1", labels={"region": "eu-west-1"})
    targets = [
        make_target(east, name="ep-default", is_default=True),
        make_target(east, name="ns-production", labels={"env": "production"}),
        make_target(west, name="ep-default-west", is_default=True),
    ]
    resolver = make_reconciler(targets)

    result = await resolver.resolve(WorkRequirements(selectors={"region": "ap-southeast-1"}))

    assert result.outcome is ResolveOutcome.NO_MATCHING_TARGETS
    assert result.available_targets == []
    assert {item.reason for item in result.ineligible_targets} == {IneligibilityReason.SELECTOR_MISMATCH}


@pytest.mark.asyncio
async def test_empty_selectors_do_not_mean_match_every_target(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster()
    default = make_target(cluster, name="ep-default", is_default=True)
    other = make_target(cluster, name="ns-production", labels={"env": "production"})
    resolver = make_reconciler([default, other])

    result = await resolver.resolve(WorkRequirements(selectors={}))

    assert _names(result) == {"ep-default"}


@pytest.mark.asyncio
async def test_default_routing_keeps_all_lifecycle_eligible_when_no_default_flag(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster()
    first = make_target(cluster, name="ns-a")
    second = make_target(cluster, name="ns-b")
    resolver = make_reconciler([first, second])

    result = await resolver.resolve(WorkRequirements())

    assert result.outcome is ResolveOutcome.MATCHED
    assert _names(result) == {"ns-a", "ns-b"}


@pytest.mark.asyncio
async def test_selectors_do_not_mix_in_non_matching_cluster_defaults(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster(labels={"region": "us-east-1"})
    default = make_target(cluster, name="ep-default", is_default=True)
    openshell = make_target(
        cluster, name="ep-openshell", backend_type=BackendType.OPENSHELL, labels={"backend_type": "openshell"}
    )
    resolver = make_reconciler([default, openshell])

    result = await resolver.resolve(WorkRequirements(selectors={"backend_type": "openshell"}))

    assert _names(result) == {"ep-openshell"}


@pytest.mark.asyncio
async def test_disabled_cluster_skips_its_targets_entirely(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    disabled = make_cluster(name="down", enabled=False)
    active = make_cluster(name="up")
    skipped = make_target(disabled, name="skipped", is_default=True)
    kept = make_target(active, name="kept", is_default=True)
    resolver = make_reconciler([skipped, kept])

    result = await resolver.resolve(WorkRequirements())

    assert _names(result) == {"kept"}
    assert skipped.id not in {item.target.id for item in result.ineligible_targets}


@pytest.mark.asyncio
async def test_non_active_and_disabled_targets_are_ineligible(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster()
    registering = make_target(cluster, name="registering", lifecycle="registering")
    draining = make_target(cluster, name="draining", lifecycle="draining")
    disabled = make_target(cluster, name="disabled", enabled=False)
    resolver = make_reconciler([registering, draining, disabled])

    result = await resolver.resolve(WorkRequirements(selectors={"gpu": "true"}))

    assert result.outcome is ResolveOutcome.NO_MATCHING_TARGETS
    reasons = {item.target.name: item.reason for item in result.ineligible_targets}
    assert reasons["registering"] is IneligibilityReason.LIFECYCLE
    assert reasons["draining"] is IneligibilityReason.LIFECYCLE
    assert reasons["disabled"] is IneligibilityReason.DISABLED


@pytest.mark.asyncio
async def test_lifecycle_denial_stops_selector_evaluation(make_cluster: MakeCluster, make_target: MakeTarget) -> None:
    cluster = make_cluster()
    target = make_target(cluster, lifecycle="failed")
    calls: list[str] = []

    class RecordingSelector(SelectorFilter):
        async def evaluate(
            self,
            eval_cluster: ClusterSnapshot,
            eval_target: ExecutionTargetSnapshot,
            requirements: WorkRequirements,
        ) -> tuple[FilterVerdict, IneligibilityReason | None]:
            calls.append("selector")
            return await super().evaluate(eval_cluster, eval_target, requirements)

    class Targets:
        async def list(self) -> list[ExecutionTargetSnapshot]:
            return [target]

    resolver = ExecutionTargetReconciler(
        Targets(),
        (LifecycleFilter(), RecordingSelector(), HealthFilter(), PolicyFilter()),
    )
    result = await resolver.resolve(WorkRequirements(selectors={"gpu": "true"}))
    assert calls == []
    assert result.ineligible_targets[0].reason is IneligibilityReason.LIFECYCLE


@pytest.mark.asyncio
async def test_multiple_matches_are_an_unordered_set(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster(labels={"region": "us-east-1"})
    one = make_target(cluster, name="ns-a", labels={"env": "production"})
    two = make_target(cluster, name="ns-b", labels={"env": "production", "gpu": "true"})
    resolver = make_reconciler([one, two])

    result = await resolver.resolve(WorkRequirements(selectors={"region": "us-east-1", "env": "production"}))

    assert result.outcome is ResolveOutcome.MATCHED
    assert _names(result) == {"ns-a", "ns-b"}


@pytest.mark.asyncio
async def test_target_label_overlay_wins_over_cluster_label(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster(labels={"region": "us-east-1"})
    overridden = make_target(cluster, name="ns-eu", labels={"region": "eu-west-1"})
    resolver = make_reconciler([overridden])

    miss = await resolver.resolve(WorkRequirements(selectors={"region": "us-east-1"}))
    hit = await resolver.resolve(WorkRequirements(selectors={"region": "eu-west-1"}))

    assert miss.outcome is ResolveOutcome.NO_MATCHING_TARGETS
    assert _names(hit) == {"ns-eu"}


@pytest.mark.asyncio
async def test_cluster_identity_pin_by_name_is_consumed(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    east = make_cluster(name="ocp-us-east-1")
    west = make_cluster(name="ocp-eu-west-1")
    east_target = make_target(east, name="east-default", is_default=True)
    west_target = make_target(west, name="west-default", is_default=True)
    resolver = make_reconciler([east_target, west_target])

    result = await resolver.resolve(WorkRequirements(selectors={"cluster": "ocp-us-east-1"}))

    assert _names(result) == {"east-default"}
    assert west_target.id not in {item.target.id for item in result.ineligible_targets}


@pytest.mark.asyncio
async def test_identity_pin_does_not_apply_default_routing(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster(name="ocp-us-east-1")
    default = make_target(cluster, name="ep-default", is_default=True)
    extra = make_target(cluster, name="ns-gpu", labels={"gpu": "true"})
    resolver = make_reconciler([default, extra])

    result = await resolver.resolve(WorkRequirements(selectors={"cluster": "ocp-us-east-1"}))

    assert _names(result) == {"ep-default", "ns-gpu"}


@pytest.mark.asyncio
async def test_no_lifecycle_eligible_target_is_no_matching_targets(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster()
    failed = make_target(cluster, lifecycle="failed", is_default=True)
    resolver = make_reconciler([failed])

    result = await resolver.resolve(WorkRequirements())

    assert result.outcome is ResolveOutcome.NO_MATCHING_TARGETS


@pytest.mark.asyncio
async def test_default_filters_match_the_documented_chain() -> None:
    names = [filt.name for filt in default_filters()]
    assert names == ["lifecycle", "selector", "health", "policy"]
