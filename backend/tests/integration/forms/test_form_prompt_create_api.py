"""Integration tests for form_prompt creation API endpoint.

Tests verify that form_prompts are correctly created through the internal
Forms API endpoint.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from syntara.core.models import User
from syntara.workflows.models.execution import Execution

FORM_PROMPTS_URL = "/api/v1/form_prompts"

# Minimal valid form definition for integration tests
_MINIMAL_FORM_DEFINITION = {
    "fields": [{"value_name": "field1", "type": "text", "label": "Test Field", "required": False}]
}


def _form_prompt_payload(
    execution_id: UUID,
    project_id: UUID,
    prompt_node_id: str = "form1",
    name: str = "Test Form",
    form_definition: dict[str, object] | None = None,
    loop_iteration_path: list[int] | None = None,
) -> dict[str, object]:
    """Build a minimal form_prompt creation request payload."""
    iteration_path = loop_iteration_path or []
    # Build temporal_activity_id from prompt_node_id and loop_iteration_path
    temporal_activity_id = prompt_node_id
    if iteration_path:
        temporal_activity_id += "".join(f"_iter_{i}" for i in iteration_path)

    return {
        "execution_id": str(execution_id),
        "project_id": str(project_id),
        "prompt_node_id": prompt_node_id,
        "name": name,
        "form_definition": form_definition or _MINIMAL_FORM_DEFINITION,
        "loop_iteration_path": iteration_path,
        "temporal_activity_id": temporal_activity_id,
    }


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormPromptCreateAPI:
    """API integration tests for form_prompt creation."""

    async def test_create_form_prompt_success(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """Create form_prompt returns 201 with prompt ID."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["execution_id"] == str(exec_id)
        assert data["prompt_node_id"] == "form1"
        assert data["status"] == "pending"

    async def test_create_form_prompt_with_responders(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
        test_user: User,
    ) -> None:
        """Create form_prompt with responder_user_ids stores responders."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)
        payload["responder_user_ids"] = [str(test_user.id)]

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["execution_id"] == str(exec_id)

    async def test_create_form_prompt_with_message(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """Create form_prompt with message field succeeds (message not in summary response)."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)
        payload["message"] = "Please fill out this form carefully"

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        # FormPromptSummary doesn't include message (only 8 minimal fields)
        assert "id" in data
        assert data["execution_id"] == str(exec_id)

    async def test_create_duplicate_form_prompt_returns_409(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
    ) -> None:
        """Creating duplicate form_prompt (same execution_id, prompt_node_id, loop_iteration_path) returns 409."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id, prompt_node_id="form1")

        # First request succeeds
        response1 = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert response1.status_code == 201

        # Second request with same keys should fail
        response2 = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert response2.status_code == 409

    async def test_list_form_prompts_by_execution(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """List form_prompts filtered by execution_id returns matching prompts."""
        exec_id = test_execution.id

        # Create two form_prompts for same execution
        payload1 = _form_prompt_payload(exec_id, test_execution.project_id, prompt_node_id="form1", name="Form 1")
        payload2 = _form_prompt_payload(exec_id, test_execution.project_id, prompt_node_id="form2", name="Form 2")

        response1 = await jwt_client.post(FORM_PROMPTS_URL, json=payload1)
        response2 = await jwt_client.post(FORM_PROMPTS_URL, json=payload2)
        assert response1.status_code == 201
        assert response2.status_code == 201

        # List by execution
        list_response = await jwt_client.get(FORM_PROMPTS_URL, params={"execution_id": str(exec_id)})
        assert list_response.status_code == 200

        data = list_response.json()
        assert "resources" in data
        assert len(data["resources"]) == 2

        prompt_names = {p["name"] for p in data["resources"]}
        assert "Form 1" in prompt_names
        assert "Form 2" in prompt_names

    async def test_batch_update_form_prompt_status(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """Batch update form_prompt status via /form_prompts/batch endpoint."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)

        # Create prompt
        create_response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert create_response.status_code == 201
        prompt_id = create_response.json()["id"]

        # Batch update to expired
        batch_payload = {"updates": [{"prompt_id": prompt_id, "status": "expired"}]}
        batch_response = await jwt_client.post(f"{FORM_PROMPTS_URL}/batch", json=batch_payload)

        assert batch_response.status_code == 200
        batch_result = batch_response.json()
        assert batch_result["total_success"] == 1
        assert batch_result["total_failed"] == 0

    async def test_create_form_prompt_with_loop_iteration_path(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
    ) -> None:
        """Create form_prompt with loop_iteration_path stores the path."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id, loop_iteration_path=[0, 1])

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["loop_iteration_path"] == [0, 1]
        assert data["temporal_activity_id"] == "form1_iter_0_iter_1"
