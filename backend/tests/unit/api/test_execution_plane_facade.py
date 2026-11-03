"""Contract tests for the AO Execution Plane facade."""

from __future__ import annotations

from typing import get_type_hints

import pytest
from execution_plane_client.models.execution_target import ExecutionTargetListParams, ExecutionTargetRead
from execution_plane_client.models.shared import ResourcesResponse
from execution_plane_client.models.work_item import WorkItemListParams, WorkItemRead
from pydantic import ValidationError

from syntara.api import execution_plane_facade as facade


def test_execution_target_facade_validates_typed_placement() -> None:
    response = ExecutionTargetRead.model_validate(
        {
            "id": "7beaf7e4-0000-4000-8000-000000000001",
            "cluster_id": "7beaf7e4-0000-4000-8000-000000000002",
            "name": "workers",
            "backend_type": "kubernetes",
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
            "status_message": None,
            "last_ran_at": None,
        }
    )

    assert response.placement.type == "kubernetes"
    assert response.placement.namespace == "ep-workers"
    assert response.model_dump(mode="json")["placement"]["node_selectors"] == ["kubernetes.io/os=linux"]


def test_execution_plane_facade_uses_shared_client_models() -> None:
    assert get_type_hints(facade.create_execution_target)["return"] is ExecutionTargetRead
    assert get_type_hints(facade.list_execution_targets)["return"] == ResourcesResponse[ExecutionTargetRead]
    assert get_type_hints(facade.list_work_items)["return"] == ResourcesResponse[WorkItemRead]
    assert get_type_hints(facade.list_execution_targets)["params"] is ExecutionTargetListParams
    assert get_type_hints(facade.list_work_items)["params"] is WorkItemListParams


def test_execution_target_facade_rejects_the_old_flat_namespace_contract() -> None:
    with pytest.raises(ValidationError):
        ExecutionTargetRead.model_validate(
            {
                "id": "7beaf7e4-0000-4000-8000-000000000001",
                "cluster_id": "7beaf7e4-0000-4000-8000-000000000002",
                "name": "workers",
                "backend_type": "kubernetes",
                "endpoint": "https://cluster.example",
                "namespace": "ep-workers",
                "status": "active",
                "enabled": True,
                "is_default": True,
                "labels": {},
                "created_at": "2026-10-02T00:00:00Z",
            }
        )
