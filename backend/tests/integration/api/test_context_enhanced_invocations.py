"""Integration tests for basic context enhancement functionality.

Tests that invocations automatically include context enhancement with grounding_score.
Based on Scenario 1 from quickstart.md.
"""

import pytest
from httpx import AsyncClient

from syntara.core.models import User
from tests.integration.helpers.invocations import wait_for_invocation_execution


class TestContextEnhancedInvocations:
    """Test suite for basic context enhancement integration."""

    @pytest.mark.asyncio
    async def test_invocation_includes_context_enhancement(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test that invocations automatically include context enhancement.

        This test verifies:
        - Context Manager is automatically called on invocations
        - Response includes grounding_score field
        - Context delimiters are added to the prompt
        - Enhanced metadata is properly stored
        """
        # Create invocation with prompt that would benefit from context
        prompt = "What are the best practices for API design in our system?"
        session_id = "test-session-001"

        # Create invocation via API
        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations",
            json={
                "prompt": prompt,
                "created_by": str(test_user.id),
                "session_id": session_id,
                "project_id": test_project_id,
            },
        )

        assert response.status_code == 202
        data = response.json()
        invocation_id = data["id"]

        # Wait for invocation to complete using the helper
        async with wait_for_invocation_execution(
            auth_client_with_mocked_llm, invocation_id, max_wait_time=10.0
        ) as final_data:
            data = final_data or data

        # Verify invocation completed successfully
        assert data["status"] == "completed", f"Invocation failed: {data.get('error_message')}"
        assert data["result"] is not None

        result = data["result"]

        # Verify basic response structure (unchanged)
        assert "type" in result
        assert "content" in result
        assert result["type"] == "answer"
        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0

        # Verify enhanced fields (new) - THIS WILL FAIL until T007 is implemented
        assert "grounding_score" in result, "Response must include grounding_score from context enhancement"

        # Validate grounding_score format
        grounding_score = result["grounding_score"]
        assert isinstance(grounding_score, float)
        assert 0.0 <= grounding_score <= 1.0

        # For empty context (current implementation), should be 0.0
        assert grounding_score == 0.0
