"""Contract tests for the AO Execution Plane facade."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from syntara.api.execution_plane_facade import ExecutionTargetFacadeRead


def test_execution_target_facade_validates_typed_placement() -> None:
    response = ExecutionTargetFacadeRead.model_validate(
        {
            "id": "7beaf7e4-0000-4000-8000-000000000001",
            "cluster_id": "7beaf7e4-0000-4000-8000-000000000002",
            "name": "workers",
            "backend_type": "vanilla_k8s",
            "endpoint": "https://cluster.example",
            "placement": {
                "type": "kubernetes",
                "namespace": "ep-workers",
                "node_selectors": ["kubernetes.io/os=linux"],
                "tolerations": ["dedicated=execution:NoSchedule"],
            },
            "status": "active",
            "enabled": True,
            "is_default": True,
            "labels": {},
            "created_at": "2026-10-02T00:00:00Z",
        }
    )

    assert response.placement.type == "kubernetes"
    assert response.placement.namespace == "ep-workers"
    assert response.model_dump(mode="json")["placement"]["node_selectors"] == ["kubernetes.io/os=linux"]


def test_execution_target_facade_rejects_the_old_flat_namespace_contract() -> None:
    with pytest.raises(ValidationError):
        ExecutionTargetFacadeRead.model_validate(
            {
                "id": "7beaf7e4-0000-4000-8000-000000000001",
                "cluster_id": "7beaf7e4-0000-4000-8000-000000000002",
                "name": "workers",
                "backend_type": "vanilla_k8s",
                "endpoint": "https://cluster.example",
                "namespace": "ep-workers",
                "status": "active",
                "enabled": True,
                "is_default": True,
                "labels": {},
                "created_at": "2026-10-02T00:00:00Z",
            }
        )
