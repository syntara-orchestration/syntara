"""Exact-AND matching and Cluster identity affinity helpers."""

from __future__ import annotations

from collections.abc import Callable

from execution_plane.execution_target_reconciler.matching import (
    any_cluster_identity_pinned,
    cluster_identity_tokens,
    cluster_is_identity_pinned,
    effective_labels,
    matches_selectors,
    remaining_selectors_after_cluster_affinity,
)
from execution_plane.execution_target_reconciler.types import ClusterSnapshot, ExecutionTargetSnapshot

MakeCluster = Callable[..., ClusterSnapshot]
MakeTarget = Callable[..., ExecutionTargetSnapshot]


def test_extra_target_labels_do_not_prevent_a_match() -> None:
    labels = {"gpu": "true", "region": "eu"}
    assert matches_selectors(labels, {"gpu": "true"}) is True


def test_missing_key_or_different_value_is_a_mismatch() -> None:
    assert matches_selectors({"gpu": "true"}, {"gpu": "true", "region": "eu"}) is False
    assert matches_selectors({"gpu": "false"}, {"gpu": "true"}) is False
    assert matches_selectors({}, {"gpu": "true"}) is False


def test_empty_selectors_match_any_label_set() -> None:
    assert matches_selectors({"gpu": "true"}, {}) is True
    assert matches_selectors({}, {}) is True


def test_effective_labels_overlay_target_values_on_cluster_labels(
    make_cluster: MakeCluster, make_target: MakeTarget
) -> None:
    cluster = make_cluster(labels={"region": "us-east-1", "cluster": "prod-a"})
    target = make_target(cluster, labels={"gpu": "true", "region": "eu-west-1"})
    assert effective_labels(cluster, target) == {
        "region": "eu-west-1",
        "cluster": "prod-a",
        "gpu": "true",
    }


def test_cluster_identity_tokens_are_id_and_name(make_cluster: MakeCluster) -> None:
    cluster = make_cluster(name="ocp-us-east-1")
    assert cluster_identity_tokens(cluster) == frozenset({str(cluster.id), "ocp-us-east-1"})


def test_identity_pin_consumes_matching_selector_values(make_cluster: MakeCluster) -> None:
    cluster = make_cluster(name="ocp-us-east-1")
    remaining = remaining_selectors_after_cluster_affinity(
        cluster,
        {"cluster": "ocp-us-east-1", "env": "production"},
    )
    assert remaining == {"env": "production"}
    assert cluster_is_identity_pinned(cluster, {"cluster": "ocp-us-east-1"}) is True
    other = make_cluster(name="ocp-eu-west-1")
    assert any_cluster_identity_pinned([cluster, other], {"cluster": "ocp-us-east-1"}) is True
    assert any_cluster_identity_pinned([cluster, other], {"region": "us-east-1"}) is False
