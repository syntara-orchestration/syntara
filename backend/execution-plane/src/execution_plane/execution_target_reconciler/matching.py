"""Exact-AND selector matching against effective labels, plus Cluster identity affinity."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from execution_plane.execution_target_reconciler.types import ClusterSnapshot, ExecutionTargetSnapshot


def effective_labels(cluster: ClusterSnapshot, target: ExecutionTargetSnapshot) -> dict[str, str]:
    """Merge Cluster labels with ExecutionTarget labels. Target values win on key clashes."""
    return {**cluster.labels, **target.labels}


def matches_selectors(labels: Mapping[str, str], selectors: Mapping[str, str]) -> bool:
    """Return whether every requested key exists on labels with that exact value."""
    return all(labels.get(key) == value for key, value in selectors.items())


def cluster_identity_tokens(cluster: ClusterSnapshot) -> frozenset[str]:
    """Values that pin a Cluster: its id string and its name."""
    return frozenset({str(cluster.id), cluster.name})


def cluster_is_identity_pinned(cluster: ClusterSnapshot, selectors: Mapping[str, str]) -> bool:
    """Return whether any selector value equals this Cluster's id or name."""
    return bool(cluster_identity_tokens(cluster) & set(selectors.values()))


def any_cluster_identity_pinned(clusters: Sequence[ClusterSnapshot], selectors: Mapping[str, str]) -> bool:
    """Return whether any Cluster is pinned by id or name in the selector map."""
    return any(cluster_is_identity_pinned(cluster, selectors) for cluster in clusters)


def remaining_selectors_after_cluster_affinity(
    cluster: ClusterSnapshot,
    selectors: Mapping[str, str],
) -> dict[str, str]:
    """Drop keys whose value pinned this Cluster by id or name. Other keys stay for label matching."""
    tokens = cluster_identity_tokens(cluster)
    return {key: value for key, value in selectors.items() if value not in tokens}
