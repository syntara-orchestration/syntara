"""Tests for the shared database-store lifecycle base class."""

from execution_plane.cluster.cluster_store import ClusterStore
from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
from execution_plane.store_base import StoreBase
from execution_plane.work_store import WorkStore


def test_database_stores_share_the_store_lifecycle_base() -> None:
    """All database-backed stores use the common resource lifecycle implementation."""
    assert issubclass(WorkStore, StoreBase)
    assert issubclass(ClusterStore, StoreBase)
    assert issubclass(ExecutionTargetStore, StoreBase)
