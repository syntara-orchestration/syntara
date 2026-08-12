"""Integration tests for context quality validation and grounding score metrics.

Tests that context enhancement provides meaningful quality improvements and metrics.
Based on Scenario 4 from quickstart.md.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from syntara.agent_orchestrator.context_manager import ContextManagerPlanner
from syntara.agent_orchestrator.context_manager.models import ContextPackage
from syntara.core.models import User
from tests.fixtures.settings import FakeSettingsCache
from tests.integration.helpers.invocations import wait_for_invocation_execution


class TestContextQualityMetrics:
    """Test suite for context quality validation and grounding score accuracy."""

    @pytest.fixture(autouse=True)
    def _mock_runtime_settings(  # type: ignore[misc]
        self, override_runtime_settings: Callable[..., AbstractContextManager[FakeSettingsCache]]
    ) -> None:
        """Auto-mock get_runtime_settings for all context quality tests."""
        with override_runtime_settings():
            yield

    @pytest.mark.asyncio
    async def test_grounding_score_reflects_context_quality(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test that grounding scores accurately reflect context quality.

        This verifies:
        - Empty context returns grounding_score = 0.0
        - High-quality context returns higher grounding scores
        - Grounding scores are in valid range (0.0-1.0)
        """
        # Test 1: Empty context (current minimal implementation)
        prompt_empty_context = "Simple greeting that needs no context"
        session_id = "empty-context-test"

        # Create invocation via API
        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations",
            json={
                "prompt": prompt_empty_context,
                "created_by": str(test_user.id),
                "session_id": session_id,
                "project_id": test_project_id,
            },
        )

        assert response.status_code == 202
        data = response.json()
        invocation_id = data["id"]

        # Wait for completion using the helper
        async with wait_for_invocation_execution(
            auth_client_with_mocked_llm, invocation_id, max_wait_time=10.0
        ) as final_data:
            data = final_data or data

        assert data["status"] == "completed", f"Invocation failed: {data.get('error_message')}"
        assert data["result"] is not None
        result = data["result"]

        # Empty context should have grounding score 0.0
        assert "grounding_score" in result, "Response must include grounding_score"
        grounding_score = result["grounding_score"]
        assert isinstance(grounding_score, float)
        assert grounding_score == 0.0, "Empty context should have grounding score 0.0"

        # Test 2: Simulate high-quality context (for future when context is populated)
        mock_context_package = ContextPackage(
            payload={
                "relevant_docs": "High-quality contextual information about the query topic",
                "related_examples": "Specific examples relevant to the user's question",
            },
            grounding_score=0.85,  # High quality context
            package_metadata={"test_metadata": "test-trace-123"},
            citations=["file-id-doc1", "file-id-doc2"],
        )

        with patch.object(ContextManagerPlanner, "plan_request", return_value=mock_context_package):
            prompt_with_context = "Complex technical question requiring context"
            session_id_context = "high-context-test"

            # Create context invocation via API
            response = await auth_client_with_mocked_llm.post(
                "/api/v1/invocations",
                json={
                    "prompt": prompt_with_context,
                    "created_by": str(test_user.id),
                    "session_id": session_id_context,
                    "project_id": test_project_id,
                },
            )

            assert response.status_code == 202
            context_data = response.json()
            context_invocation_id = context_data["id"]

            # Wait for completion using the helper
            async with wait_for_invocation_execution(
                auth_client_with_mocked_llm, context_invocation_id, max_wait_time=10.0
            ) as final_data:
                context_data = final_data or context_data

            assert context_data["status"] == "completed", (
                f"Context invocation failed: {context_data.get('error_message')}"
            )
            assert context_data["result"] is not None
            result_context = context_data["result"]

            # High-quality context should have higher grounding score
            assert "grounding_score" in result_context
            context_grounding_score = result_context["grounding_score"]
            assert isinstance(context_grounding_score, float)
            assert context_grounding_score == 0.85, "Should reflect context package grounding score"

    @pytest.mark.asyncio
    async def test_grounding_score_range_validation(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test that grounding scores are always in valid range (0.0-1.0)."""
        test_scores = [0.0, 0.25, 0.5, 0.75, 1.0]

        for score in test_scores:
            mock_context_package = ContextPackage(
                payload={"test": "data"},
                grounding_score=score,
                package_metadata={"test_metadata": f"test-{score}"},
                citations=[],
            )

            with patch.object(ContextManagerPlanner, "plan_request", return_value=mock_context_package):
                prompt = f"Test prompt for score {score}"
                session_id = f"score-test-{score}"

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

                # Wait for completion using the helper
                async with wait_for_invocation_execution(
                    auth_client_with_mocked_llm, invocation_id, max_wait_time=10.0
                ) as final_data:
                    data = final_data or data

                assert data["status"] == "completed", f"Invocation failed: {data.get('error_message')}"
                assert data["result"] is not None
                result = data["result"]

                assert "grounding_score" in result
                returned_score = result["grounding_score"]
                assert isinstance(returned_score, float)
                assert 0.0 <= returned_score <= 1.0, f"Score {returned_score} must be in range 0.0-1.0"
                assert returned_score == score, f"Should preserve original score {score}"

    @pytest.mark.asyncio
    async def test_context_enhancement_completeness(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test that context enhancement provides complete information for quality assessment."""
        mock_context_package = ContextPackage(
            payload={"context": "test content"},
            grounding_score=0.75,
            package_metadata={
                "context_status": "populated",
                "processing_time": 0.250,
            },
            citations=["file-id-doc1", "file-id-api-spec"],
        )

        with patch.object(ContextManagerPlanner, "plan_request", return_value=mock_context_package):
            prompt = "Test metadata completeness"
            session_id = "metadata-completeness-test"

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

            # Wait for completion using the helper
            async with wait_for_invocation_execution(
                auth_client_with_mocked_llm, invocation_id, max_wait_time=10.0
            ) as final_data:
                data = final_data or data

            assert data["status"] == "completed", f"Invocation failed: {data.get('error_message')}"
            assert data["result"] is not None
            result = data["result"]

            # Verify core quality metrics
            assert "grounding_score" in result
            assert result["grounding_score"] == 0.75

            # If context_enhancement is exposed in response, verify structure
            if "context_enhancement" in result:
                context_enhancement = result["context_enhancement"]
                assert isinstance(context_enhancement, dict)

                # Should include citations for quality assessment
                if "citations" in context_enhancement:
                    citations = context_enhancement["citations"]
                    assert isinstance(citations, list)
                    assert len(citations) == 2
                    # Citations are now file_id strings
                    assert all(isinstance(c, str) for c in citations)

    @pytest.mark.asyncio
    async def test_empty_vs_populated_context_distinction(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test that system can distinguish between empty and populated context scenarios.

        This helps validate that quality metrics are meaningful.
        """
        # Test 1: Explicitly empty context
        mock_empty_context = ContextPackage(
            payload={},
            grounding_score=0.0,
            package_metadata={"context_status": "empty"},
            citations=[],
        )

        with patch.object(ContextManagerPlanner, "plan_request", return_value=mock_empty_context):
            # Create empty context invocation via API
            response = await auth_client_with_mocked_llm.post(
                "/api/v1/invocations",
                json={
                    "prompt": "Test empty context",
                    "created_by": str(test_user.id),
                    "session_id": "empty-context-distinction",
                    "project_id": test_project_id,
                },
            )

            assert response.status_code == 202
            empty_data = response.json()
            empty_invocation_id = empty_data["id"]

            # Wait for completion using the helper
            async with wait_for_invocation_execution(
                auth_client_with_mocked_llm, empty_invocation_id, max_wait_time=10.0
            ) as final_data:
                empty_data = final_data or empty_data

            assert empty_data["status"] == "completed", (
                f"Empty context invocation failed: {empty_data.get('error_message')}"
            )
            assert empty_data["result"] is not None
            result_empty = empty_data["result"]
            assert result_empty["grounding_score"] == 0.0

        # Test 2: Populated context
        mock_populated_context = ContextPackage(
            payload={"docs": "relevant content"},
            grounding_score=0.6,
            package_metadata={"context_status": "populated"},
            citations=["file-id-test"],
        )

        with patch.object(ContextManagerPlanner, "plan_request", return_value=mock_populated_context):
            # Create populated context invocation via API
            response = await auth_client_with_mocked_llm.post(
                "/api/v1/invocations",
                json={
                    "prompt": "Test populated context",
                    "created_by": str(test_user.id),
                    "session_id": "populated-context-distinction",
                    "project_id": test_project_id,
                },
            )

            assert response.status_code == 202
            populated_data = response.json()
            populated_invocation_id = populated_data["id"]

            # Wait for completion using the helper
            async with wait_for_invocation_execution(
                auth_client_with_mocked_llm, populated_invocation_id, max_wait_time=10.0
            ) as final_data:
                populated_data = final_data or populated_data

            assert populated_data["status"] == "completed", (
                f"Populated context invocation failed: {populated_data.get('error_message')}"
            )
            assert populated_data["result"] is not None
            result_populated = populated_data["result"]
            assert result_populated["grounding_score"] == 0.6

        # Verify distinction is clear
        empty_score = result_empty["grounding_score"]
        populated_score = result_populated["grounding_score"]
        assert isinstance(empty_score, int | float)
        assert isinstance(populated_score, int | float)
        assert empty_score < populated_score, "Populated context should have higher grounding score than empty context"
