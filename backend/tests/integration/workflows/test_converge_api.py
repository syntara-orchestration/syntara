"""Integration tests for converge node API operations (CRUD).

Tests verify that converge node configurations are correctly handled through
the workflow REST API endpoints.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

WORKFLOWS_URL = "/api/v1/workflows"


def _converge_workflow_payload(
    name: str,
    converge_config: dict[str, object],
    project_id: str,
    branch_count: int = 2,
) -> dict[str, object]:
    """Build a minimal workflow payload with a converge node."""
    branches = [
        {
            "id": f"branch_{chr(97 + i)}",
            "name": f"Branch {chr(65 + i)}",
            "type": "script_bash",
            "parameters": {"code": f'echo "Branch {chr(65 + i)}"'},
        }
        for i in range(branch_count)
    ]

    return {
        "name": name,
        "description": f"Test converge: {name}",
        "project_id": project_id,
        "workflow_definition": {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                *branches,
                {
                    "id": "converge_node",
                    "name": "Converge Node",
                    "type": "converge",
                    "parameters": converge_config,
                },
                {
                    "id": "final_action",
                    "name": "Final Action",
                    "type": "script_bash",
                    "parameters": {"code": 'echo "Done"'},
                },
            ],
            "edges": [
                *[{"from": "trigger", "to": f"branch_{chr(97 + i)}"} for i in range(branch_count)],
                *[{"from": f"branch_{chr(97 + i)}", "to": "converge_node"} for i in range(branch_count)],
                {"from": "converge_node", "to": "final_action"},
            ],
        },
    }


@pytest.mark.integration
@pytest.mark.asyncio
class TestConvergeCRUD:
    """CRUD happy-path tests for converge node workflows."""

    async def test_create_workflow_with_converge_all_strategy(
        self, jwt_client: AsyncClient, test_project_id: UUID
    ) -> None:
        """Create workflow with converge node using 'all' strategy."""
        payload = _converge_workflow_payload(
            "test-converge-all-strategy",
            {"strategy": "all"},
            project_id=str(test_project_id),
        )

        response = await jwt_client.post(WORKFLOWS_URL, json=payload)

        assert response.status_code == 201
        workflow = response.json()
        assert workflow["name"] == "test-converge-all-strategy"
        assert workflow["current_version"] == 1

    async def test_create_workflow_with_converge_any_strategy(
        self, jwt_client: AsyncClient, test_project_id: UUID
    ) -> None:
        """Create workflow with converge node using 'any' strategy."""
        payload = _converge_workflow_payload(
            "test-converge-any-strategy",
            {"strategy": "any", "n_required": 2},
            project_id=str(test_project_id),
            branch_count=3,
        )

        response = await jwt_client.post(WORKFLOWS_URL, json=payload)

        assert response.status_code == 201
        workflow = response.json()
        assert workflow["name"] == "test-converge-any-strategy"
        assert workflow["current_version"] == 1

    async def test_get_workflow_preserves_converge_config(self, jwt_client: AsyncClient, test_project_id: UUID) -> None:
        """Verify GET workflow preserves converge node configuration."""
        converge_config = {
            "strategy": "any",
            "n_required": 2,
        }
        payload = _converge_workflow_payload(
            "test-converge-config-preservation",
            converge_config,
            project_id=str(test_project_id),
            branch_count=3,
        )

        create_response = await jwt_client.post(WORKFLOWS_URL, json=payload)
        assert create_response.status_code == 201
        workflow_id = create_response.json()["id"]

        get_response = await jwt_client.get(f"{WORKFLOWS_URL}/{workflow_id}")
        assert get_response.status_code == 200

        definition = get_response.json()["version"]["workflow_definition"]
        converge_nodes = [n for n in definition["nodes"] if n["type"] == "converge"]
        assert len(converge_nodes) == 1
        assert converge_nodes[0]["parameters"] == converge_config

    async def test_update_workflow_converge_configuration(self, jwt_client: AsyncClient, test_project_id: UUID) -> None:
        """Update converge node configuration via PATCH."""
        payload = _converge_workflow_payload(
            "test-converge-update",
            {"strategy": "all"},
            project_id=str(test_project_id),
        )

        create_response = await jwt_client.post(WORKFLOWS_URL, json=payload)
        assert create_response.status_code == 201
        workflow_id = create_response.json()["id"]

        updated_config = {
            "strategy": "any",
            "n_required": 1,
        }
        update_payload = _converge_workflow_payload(
            "test-converge-update",
            updated_config,
            project_id=str(test_project_id),
        )
        update_payload.pop("name")
        update_payload.pop("description")
        update_payload["change_description"] = "Updated converge strategy from all to any"

        update_response = await jwt_client.patch(
            f"{WORKFLOWS_URL}/{workflow_id}",
            json=update_payload,
        )
        assert update_response.status_code == 200

        updated_workflow = update_response.json()
        assert updated_workflow["current_version"] == 2

        definition = updated_workflow["version"]["workflow_definition"]
        converge_nodes = [n for n in definition["nodes"] if n["type"] == "converge"]
        assert len(converge_nodes) == 1
        assert converge_nodes[0]["parameters"] == updated_config

    async def test_delete_workflow_with_converge_node(self, jwt_client: AsyncClient, test_project_id: UUID) -> None:
        """Delete workflow containing converge node."""
        payload = _converge_workflow_payload(
            "test-converge-delete",
            {"strategy": "all"},
            project_id=str(test_project_id),
            branch_count=2,
        )

        create_response = await jwt_client.post(WORKFLOWS_URL, json=payload)
        assert create_response.status_code == 201
        workflow_id = create_response.json()["id"]

        get_response = await jwt_client.get(f"{WORKFLOWS_URL}/{workflow_id}")
        assert get_response.status_code == 200

        delete_response = await jwt_client.delete(f"{WORKFLOWS_URL}/{workflow_id}")
        assert delete_response.status_code == 204

        get_deleted_response = await jwt_client.get(f"{WORKFLOWS_URL}/{workflow_id}")
        assert get_deleted_response.status_code == 404

        list_response = await jwt_client.get(WORKFLOWS_URL)
        assert list_response.status_code == 200
        workflow_ids = [w["id"] for w in list_response.json()["resources"]]
        assert workflow_id not in workflow_ids
