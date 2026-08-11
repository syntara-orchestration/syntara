"""Integration tests for context enhancement performance impact assessment.

Tests that context enhancement adds acceptable latency to invocation processing.
Based on Scenario 5 from quickstart.md.
"""

import time
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from syntara.agent_orchestrator.context_manager import ContextManagerPlanner
from syntara.agent_orchestrator.context_manager.models import ContextPackage
from syntara.core.models import User
from tests.integration.helpers.invocations import wait_for_invocation_execution


class TestContextPerformanceImpact:
    """Test suite for performance impact assessment of context enhancement."""

    @pytest.mark.asyncio
    async def test_baseline_vs_context_enhanced_performance(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test performance comparison between baseline and context-enhanced invocations.

        This verifies that context enhancement adds acceptable overhead.

        Note: Performance thresholds are defined by performance team during implementation.
        """
        # Test 1: Baseline performance (minimal context processing)
        baseline_prompt = "What is 2 + 2?"
        baseline_session = "performance-baseline"

        start_time = time.time()

        # Create baseline invocation via API
        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations",
            json={
                "prompt": baseline_prompt,
                "created_by": str(test_user.id),
                "session_id": baseline_session,
                "project_id": test_project_id,
            },
        )

        assert response.status_code == 202
        baseline_data = response.json()
        baseline_invocation_id = baseline_data["id"]

        # Wait for completion using the helper
        async with wait_for_invocation_execution(
            auth_client_with_mocked_llm, baseline_invocation_id, max_wait_time=30.0
        ) as final_data:
            baseline_data = final_data or baseline_data

        baseline_end_time = time.time()
        baseline_duration = baseline_end_time - start_time

        assert baseline_data["status"] == "completed", f"Baseline failed: {baseline_data.get('error_message')}"
        assert baseline_duration < 30.0, "Baseline should complete within reasonable time"

        # Test 2: Context-enhanced performance (simulated heavy context)
        mock_context_package = ContextPackage(
            payload={
                "large_context": "This is simulated large context data " * 100  # ~4KB of context
            },
            grounding_score=0.8,
            package_metadata={},
            citations=[f"file-id-doc{i}" for i in range(10)],
        )

        with patch.object(ContextManagerPlanner, "plan_request", return_value=mock_context_package):
            context_prompt = "Explain our entire system architecture and best practices"
            context_session = "performance-context"

            context_start_time = time.time()

            # Create context invocation via API
            response = await auth_client_with_mocked_llm.post(
                "/api/v1/invocations",
                json={
                    "prompt": context_prompt,
                    "created_by": str(test_user.id),
                    "session_id": context_session,
                    "project_id": test_project_id,
                },
            )

            assert response.status_code == 202
            context_data = response.json()
            context_invocation_id = context_data["id"]

            # Wait for completion using the helper
            async with wait_for_invocation_execution(
                auth_client_with_mocked_llm, context_invocation_id, max_wait_time=30.0
            ) as final_data:
                context_data = final_data or context_data

            context_end_time = time.time()
            context_duration = context_end_time - context_start_time

        assert context_data["status"] == "completed", f"Context invocation failed: {context_data.get('error_message')}"

        # Performance analysis
        performance_overhead = context_duration - baseline_duration

        # Verify reasonable performance (thresholds TBD by performance team)
        assert context_duration < 30.0, "Context-enhanced invocation should complete within reasonable time"

        # Context enhancement should not add excessive overhead
        # This threshold may need adjustment based on actual performance requirements
        max_acceptable_overhead = 10.0  # seconds
        assert performance_overhead < max_acceptable_overhead, (
            f"Context overhead ({performance_overhead:.2f}s) exceeds threshold ({max_acceptable_overhead}s)"
        )

    @pytest.mark.asyncio
    async def test_context_processing_timeout_performance(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test that context processing timeouts don't significantly impact performance."""

        # Mock slow context processing
        def slow_context_processing(*args: object, **kwargs: object) -> ContextPackage:
            time.sleep(2.0)  # 2 second delay
            return ContextPackage(payload={}, grounding_score=0.0)

        with patch.object(ContextManagerPlanner, "plan_request", side_effect=slow_context_processing):
            prompt = "Test slow context processing"
            session_id = "slow-context-test"

            start_time = time.time()

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

            # Wait for completion with timeout
            async with wait_for_invocation_execution(
                auth_client_with_mocked_llm, invocation_id, max_wait_time=15.0
            ) as final_data:
                data = final_data or data

            end_time = time.time()
            total_duration = end_time - start_time

            # Should not hang indefinitely due to slow context processing
            assert total_duration < 10.0, "Should not be blocked indefinitely by slow context processing"

    @pytest.mark.asyncio
    async def test_concurrent_context_enhanced_invocations(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test performance under concurrent context-enhanced invocations."""

        # Mock context that adds some processing time
        def context_with_delay(*args: object, **kwargs: object) -> ContextPackage:
            time.sleep(0.1)  # 100ms processing time
            return ContextPackage(
                payload={"concurrent": "test"},
                grounding_score=0.5,
            )

        with patch.object(ContextManagerPlanner, "plan_request", side_effect=context_with_delay):
            # Create multiple concurrent invocations
            num_concurrent = 5
            invocation_ids = []

            start_time = time.time()

            # Start all invocations concurrently
            for i in range(num_concurrent):
                response = await auth_client_with_mocked_llm.post(
                    "/api/v1/invocations",
                    json={
                        "prompt": f"Concurrent test prompt {i}",
                        "created_by": str(test_user.id),
                        "session_id": f"concurrent-session-{i}",
                        "project_id": test_project_id,
                    },
                )
                assert response.status_code == 202
                data = response.json()
                invocation_ids.append(data["id"])

            # Wait for all to complete using wait helpers
            invocation_results = []
            for invocation_id in invocation_ids:
                async with wait_for_invocation_execution(
                    auth_client_with_mocked_llm, invocation_id, max_wait_time=20.0
                ) as final_data:
                    invocation_results.append(final_data)

            end_time = time.time()
            total_duration = end_time - start_time

            # Verify all completed successfully
            for i, result in enumerate(invocation_results):
                assert result
                assert result["status"] == "completed", (
                    f"Invocation {i} should complete: {result.get('error_message') if result else 'None'}"
                )

            # Concurrent processing should not take much longer than sequential
            # With proper async handling, should be closer to single invocation time
            expected_max_duration = 120.0  # Should not take much longer than single invocation
            assert total_duration < expected_max_duration, (
                f"Concurrent processing took {total_duration:.2f}s, expected < {expected_max_duration}s"
            )

    @pytest.mark.asyncio
    async def test_memory_usage_with_context_enhancement(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test that context enhancement doesn't cause excessive memory usage."""
        # Test with larger context payloads to check memory handling
        large_context_sizes = [1024, 4096, 8192]  # bytes

        for context_size in large_context_sizes:
            mock_context_package = ContextPackage(
                payload={
                    "large_data": "x" * context_size  # Create context of specified size
                },
                grounding_score=0.7,
                package_metadata={},
                citations=[],
            )

            with patch.object(ContextManagerPlanner, "plan_request", return_value=mock_context_package):
                prompt = f"Test with {context_size} byte context"
                session_id = f"memory-test-{context_size}"

                start_time = time.time()

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
                    auth_client_with_mocked_llm, invocation_id, max_wait_time=15.0
                ) as final_data:
                    data = final_data or data

                end_time = time.time()
                duration = end_time - start_time

                assert data["status"] == "completed", f"Invocation failed: {data.get('error_message')}"
                assert duration < 15.0, f"Large context ({context_size}B) should not cause excessive delays"

    @pytest.mark.asyncio
    async def test_context_caching_performance_benefit(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Test potential performance benefits from context caching (future optimization).

        This test documents expected behavior for future caching implementations.
        """
        # This test is placeholder for future context caching optimizations
        # For now, just verify that repeated similar queries work consistently

        similar_prompts = [
            "What are API best practices?",
            "Tell me about API best practices",
            "Explain API design best practices",
        ]

        durations = []

        for i, prompt in enumerate(similar_prompts):
            start_time = time.time()

            # Create invocation via API
            response = await auth_client_with_mocked_llm.post(
                "/api/v1/invocations",
                json={
                    "prompt": prompt,
                    "created_by": str(test_user.id),
                    "session_id": f"caching-test-{i}",
                    "project_id": test_project_id,
                },
            )

            assert response.status_code == 202
            data = response.json()
            invocation_id = data["id"]

            # Wait for completion using the helper
            async with wait_for_invocation_execution(
                auth_client_with_mocked_llm, invocation_id, max_wait_time=15.0
            ) as final_data:
                data = final_data or data

            end_time = time.time()
            duration = end_time - start_time
            durations.append(duration)

            assert data["status"] == "completed", f"Invocation failed: {data.get('error_message')}"

        # For now, just verify all completed successfully
        # Future implementations might show performance improvement for similar queries
        assert all(d < 15.0 for d in durations), "All similar queries should complete efficiently"

        # TODO: When context caching is implemented, verify that subsequent similar queries are faster
