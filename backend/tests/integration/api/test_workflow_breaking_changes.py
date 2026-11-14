"""Integration tests for SubWorkflow breaking changes detection API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from uuid import UUID

    from httpx import AsyncClient

    from syntara.workflows.models import Workflow


async def _create_and_publish_version_with_output_schema(
    jwt_client: AsyncClient,
    workflow_id: int | UUID,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> int:
    """Helper to create and publish a version with output_schema."""
    response = await jwt_client.post(f"/workflows/{workflow_id}/versions")
    assert response.status_code == 200
    version: int = response.json()["version"]

    definition: dict[str, Any] = {
        "schema_version": "2.0.0",
        "triggers": [
            {
                "id": "subworkflow_trigger",
                "type": "subworkflow_trigger",
                "parameters": {
                    "output_schema": {
                        "type": "object",
                        "properties": properties,
                        **({"required": required} if required else {}),
                    },
                },
            }
        ],
        "nodes": [],
        "edges": [],
    }

    response = await jwt_client.put(
        f"/workflows/{workflow_id}/versions/{version}",
        json={"definition": definition},
    )
    assert response.status_code == 200

    response = await jwt_client.post(f"/workflows/{workflow_id}/versions/{version}/publish")
    assert response.status_code == 200

    return version


class TestCheckBreakingChanges:
    """Test the check-breaking-changes endpoint."""

    @pytest.mark.asyncio
    async def test_no_breaking_changes_when_no_published_version(
        self,
        jwt_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """First publish has no breaking changes."""
        # Create a version
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions")
        assert response.status_code == 200
        version = response.json()["version"]

        # Add output_schema to the draft version
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "artifact_url": {"type": "string"},
                            },
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        response = await jwt_client.put(
            f"/workflows/{test_workflow.id}/versions/{version}",
            json={"definition": definition},
        )
        assert response.status_code == 200

        # Check breaking changes
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions/{version}/check-breaking-changes")

        assert response.status_code == 200
        data = response.json()
        assert data["has_breaking_changes"] is False
        assert len(data["triggers"]) == 0

    @pytest.mark.asyncio
    async def test_detects_removed_output(
        self,
        jwt_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """Detect when an output field is removed."""
        # Create and publish a version with output_schema
        await _create_and_publish_version_with_output_schema(
            jwt_client,
            test_workflow.id,
            {
                "artifact_url": {"type": "string"},
                "build_id": {"type": "number"},
                "deployment_status": {"type": "string"},
            },
            required=["artifact_url"],
        )

        # Create a new draft version with build_id removed
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions")
        assert response.status_code == 200
        new_version = response.json()["version"]

        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "artifact_url": {"type": "string"},
                                # build_id removed
                                "deployment_status": {"type": "string"},
                            },
                            "required": ["artifact_url"],
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        response = await jwt_client.put(
            f"/workflows/{test_workflow.id}/versions/{new_version}",
            json={"definition": definition},
        )
        assert response.status_code == 200

        # Check breaking changes
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions/{new_version}/check-breaking-changes")

        assert response.status_code == 200
        data = response.json()
        assert data["has_breaking_changes"] is True
        assert len(data["triggers"]) == 1

        trigger_changes = data["triggers"][0]
        assert trigger_changes["trigger_id"] == "subworkflow_trigger"
        assert len(trigger_changes["changes"]) == 1

        change = trigger_changes["changes"][0]
        assert change["change_type"] == "removed_output"
        assert change["field_path"] == "build_id"

    @pytest.mark.asyncio
    async def test_detects_type_change(
        self,
        jwt_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """Detect when a field's type changes."""
        await _create_and_publish_version_with_output_schema(
            jwt_client,
            test_workflow.id,
            {
                "artifact_url": {"type": "string"},
                "build_id": {"type": "number"},
                "deployment_status": {"type": "string"},
            },
            required=["artifact_url"],
        )

        # Create a new draft version with deployment_status changed to object
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions")
        assert response.status_code == 200
        new_version = response.json()["version"]

        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "artifact_url": {"type": "string"},
                                "build_id": {"type": "number"},
                                "deployment_status": {"type": "object"},  # Changed from string
                            },
                            "required": ["artifact_url"],
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        response = await jwt_client.put(
            f"/workflows/{test_workflow.id}/versions/{new_version}",
            json={"definition": definition},
        )
        assert response.status_code == 200

        # Check breaking changes
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions/{new_version}/check-breaking-changes")

        assert response.status_code == 200
        data = response.json()
        assert data["has_breaking_changes"] is True

        change = data["triggers"][0]["changes"][0]
        assert change["change_type"] == "type_change"
        assert change["field_path"] == "deployment_status"
        assert change["old_type"] == "string"
        assert change["new_type"] == "object"

    @pytest.mark.asyncio
    async def test_detects_new_required_output(
        self,
        jwt_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """Detect when a new required field is added."""
        await _create_and_publish_version_with_output_schema(
            jwt_client,
            test_workflow.id,
            {
                "artifact_url": {"type": "string"},
                "build_id": {"type": "number"},
                "deployment_status": {"type": "string"},
            },
            required=["artifact_url"],
        )

        # Create a new draft version with a new required field
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions")
        assert response.status_code == 200
        new_version = response.json()["version"]

        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "artifact_url": {"type": "string"},
                                "build_id": {"type": "number"},
                                "deployment_status": {"type": "string"},
                                "new_required_field": {"type": "string"},  # New field
                            },
                            "required": ["artifact_url", "new_required_field"],  # Now required
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        response = await jwt_client.put(
            f"/workflows/{test_workflow.id}/versions/{new_version}",
            json={"definition": definition},
        )
        assert response.status_code == 200

        # Check breaking changes
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions/{new_version}/check-breaking-changes")

        assert response.status_code == 200
        data = response.json()
        assert data["has_breaking_changes"] is True

        change = data["triggers"][0]["changes"][0]
        assert change["change_type"] == "new_required_output"
        assert change["field_path"] == "new_required_field"

    @pytest.mark.asyncio
    async def test_no_breaking_changes_for_optional_field_addition(
        self,
        jwt_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """Adding a new optional field is not a breaking change."""
        await _create_and_publish_version_with_output_schema(
            jwt_client,
            test_workflow.id,
            {
                "artifact_url": {"type": "string"},
                "build_id": {"type": "number"},
                "deployment_status": {"type": "string"},
            },
            required=["artifact_url"],
        )

        # Create a new draft version with a new optional field
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions")
        assert response.status_code == 200
        new_version = response.json()["version"]

        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "artifact_url": {"type": "string"},
                                "build_id": {"type": "number"},
                                "deployment_status": {"type": "string"},
                                "new_optional_field": {"type": "string"},  # New optional field
                            },
                            "required": ["artifact_url"],
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        response = await jwt_client.put(
            f"/workflows/{test_workflow.id}/versions/{new_version}",
            json={"definition": definition},
        )
        assert response.status_code == 200

        # Check breaking changes
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions/{new_version}/check-breaking-changes")

        assert response.status_code == 200
        data = response.json()
        assert data["has_breaking_changes"] is False
        assert len(data["triggers"]) == 0

    @pytest.mark.asyncio
    async def test_404_when_workflow_not_found(self, jwt_client: AsyncClient) -> None:
        """Return 404 when workflow does not exist."""
        response = await jwt_client.post("/workflows/99999/versions/1/check-breaking-changes")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_404_when_version_not_found(
        self,
        jwt_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """Return 404 when version does not exist."""
        response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions/99999/check-breaking-changes")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_lists_published_parent_references(
        self,
        jwt_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """The output contract review identifies published parents that will use the next child version."""
        await _create_and_publish_version_with_output_schema(
            jwt_client,
            test_workflow.id,
            {"artifact_url": {"type": "string"}, "build_id": {"type": "number"}},
        )
        parent_definition = {
            "schema_version": "2.0.0",
            "name": "Parent referencing child",
            "triggers": [{"id": "parent_start", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "invoke_child",
                    "type": "sub_workflow",
                    "name": "Invoke child",
                    "parameters": {
                        "workflow_id": str(test_workflow.id),
                        "trigger_node_id": "subworkflow_trigger",
                        "input_mapping": {},
                    },
                }
            ],
            "edges": [{"from": "parent_start", "to": "invoke_child"}],
        }
        parent_response = await jwt_client.post(
            "/workflows",
            json={
                "name": "Parent referencing child",
                "project_id": str(test_workflow.project_id),
                "workflow_definition": parent_definition,
            },
        )
        assert parent_response.status_code == 201
        parent = parent_response.json()
        publish_response = await jwt_client.post(f"/workflows/{parent['id']}/versions/1/publish", json={})
        assert publish_response.status_code == 200

        draft_response = await jwt_client.post(f"/workflows/{test_workflow.id}/versions")
        assert draft_response.status_code == 200
        new_version = draft_response.json()["version"]
        changed_definition = {
            "schema_version": "2.0.0",
            "name": "Child",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {"type": "object", "properties": {"artifact_url": {"type": "string"}}}
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }
        response = await jwt_client.post(
            f"/workflows/{test_workflow.id}/versions/{new_version}/check-breaking-changes",
            json={"workflow_definition": changed_definition},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["has_breaking_changes"] is True
        assert len(result["parent_workflows"]) == 1
        reference = result["parent_workflows"][0]
        assert reference["workflow_id"] == parent["id"]
        assert reference["workflow_name"] == parent["name"]
        assert reference["step_name"] == "Invoke child"
        assert "child_version_id" not in reference
