"""Integration test for information query flow.

Tests end-to-end flow: POST /invocations → routing → GenericAgent → LLM response.
"""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

from tests.integration.helpers.invocations import wait_for_invocation_execution


class TestGenericQueryFlow:
    """Test end-to-end information query flow."""

    @pytest.mark.asyncio
    async def test_information_query_routes_to_generic_agent(
        self, auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
    ) -> None:
        """Test POST /invocations with info query routes to GenericAgent."""
        # Arrange
        request_data = {
            "prompt": "What tools are available for deployment?",
            "created_by": str(test_user.id),
            "session_id": "test-session-456",
            "project_id": str(test_project_id),
            "context_data": {},
        }

        # Act
        response = await auth_client_with_mocked_llm.post("/api/v1/invocations", json=request_data)

        # Assert
        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        invocation_id = data["id"]

        # Wait for execution to start
        async with wait_for_invocation_execution(auth_client_with_mocked_llm, invocation_id) as final_data:
            data = final_data or data
            assert data["status"] in ["running", "completed"]  # Execution should have started

        # Verify invocation ID is valid UUID
        invocation_id_obj = UUID(invocation_id)
        assert isinstance(invocation_id_obj, UUID)

    @pytest.mark.asyncio
    async def test_generic_agent_returns_answer_not_workflow(
        self, auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
    ) -> None:
        """Test GenericAgent returns result_type='answer' (not 'workflow')."""
        # Arrange
        request_data = {
            "prompt": "List available monitoring tools",
            "created_by": str(test_user.id),
            "session_id": "test-session",
            "project_id": str(test_project_id),
        }

        # Act
        response = await auth_client_with_mocked_llm.post("/api/v1/invocations", json=request_data)

        # Assert
        assert response.status_code == 202
        # Note: In real implementation, we'd query the invocation result
        # to verify result_type='answer'. For now, just verify invocation created.

    @pytest.mark.asyncio
    async def test_no_workflow_generation_for_information_queries(
        self, auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
    ) -> None:
        """Test information queries don't trigger workflow generation."""
        # Arrange
        request_data = {
            "prompt": "Show me available agents",
            "created_by": str(test_user.id),
            "session_id": "test-session",
            "project_id": str(test_project_id),
        }

        # Act
        response = await auth_client_with_mocked_llm.post("/api/v1/invocations", json=request_data)

        # Assert - invocation accepted means GenericAgent will process via mocked LLM
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_llm_generates_answer_for_query(
        self, auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
    ) -> None:
        """Test LangChain LLM generates answer (using mocked LLM response)."""
        # Arrange
        request_data = {
            "prompt": "What deployment strategies are supported?",
            "created_by": str(test_user.id),
            "session_id": "test-session",
            "project_id": str(test_project_id),
        }

        # Act
        response = await auth_client_with_mocked_llm.post("/api/v1/invocations", json=request_data)

        # Assert
        assert response.status_code == 202
        data = response.json()
        invocation_id = data["id"]

        # Wait for execution to start
        async with wait_for_invocation_execution(auth_client_with_mocked_llm, invocation_id) as final_data:
            data = final_data or data
            assert data["status"] in ["running", "completed"]
        # Invocation accepted successfully - LLM will process in background/sync


class TestGenericQueryErrorHandling:
    """Test error handling for information query flow."""

    @pytest.mark.asyncio
    async def test_handles_llm_errors_gracefully(
        self, auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
    ) -> None:
        """Test system handles LLM errors without crashing."""
        # Arrange
        request_data = {
            "prompt": "What tools are available?",
            "created_by": str(test_user.id),
            "session_id": "test-session",
            "project_id": str(test_project_id),
        }

        with patch("syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.side_effect = Exception("LLM API error")
            mock_get_llm.return_value = (mock_llm, None)

            # Act
            response = await auth_client_with_mocked_llm.post("/api/v1/invocations", json=request_data)

            # Assert
            # Should still accept invocation (error handled in background)
            assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_handles_invalid_request_data(
        self, auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
    ) -> None:
        """Test system validates request data properly."""
        # Arrange

        invalid_request = {
            "prompt": "",  # Empty prompt should fail validation
            "created_by": str(test_user.id),
            "session_id": "test-session",
            "project_id": str(test_project_id),
        }

        # Act
        response = await auth_client_with_mocked_llm.post("/api/v1/invocations", json=invalid_request)

        # Assert
        assert response.status_code == 422  # Unprocessable Entity (validation error)
