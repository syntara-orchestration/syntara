"""Unit tests for OrchestrationService._apply_provider_token_totals."""

from __future__ import annotations

from typing import Any

from syntara.agent_orchestrator.services.orchestration_service import OrchestrationService


class TestApplyProviderTokenTotals:
    """Agent Steps header should use full prompt+completion usage when available."""

    def test_overwrites_stream_estimate_with_provider_totals(self) -> None:
        result: dict[str, Any] = {
            "agent_trace": {
                "model": "test-model",
                "total_tokens": 152,  # stream-derived reasoning estimate
                "total_duration_ms": 1000,
                "steps": [{"type": "reasoning", "tokens": 152}],
            },
            "llm_token_usage_log": [
                {"input_tokens": 2729, "output_tokens": 244},
                {"input_tokens": 0, "output_tokens": 380},
            ],
        }

        OrchestrationService._apply_provider_token_totals(result)

        assert result["agent_trace"]["total_tokens"] == 3353
        assert result["tokens_used"] == 3353

    def test_falls_back_to_trace_total_without_usage_log(self) -> None:
        result: dict[str, Any] = {
            "agent_trace": {
                "model": "test-model",
                "total_tokens": 173,
                "total_duration_ms": 500,
                "steps": [{"type": "reasoning", "tokens": 173}],
            },
        }

        OrchestrationService._apply_provider_token_totals(result)

        assert result["agent_trace"]["total_tokens"] == 173
        assert result["tokens_used"] == 173

    def test_usage_log_sets_tokens_used_without_agent_trace(self) -> None:
        result: dict[str, Any] = {"llm_token_usage_log": [{"input_tokens": 10, "output_tokens": 5}]}

        OrchestrationService._apply_provider_token_totals(result)

        assert result["tokens_used"] == 15

    def test_missing_agent_trace_and_usage_log_sets_zero(self) -> None:
        result: dict[str, Any] = {}

        OrchestrationService._apply_provider_token_totals(result)

        assert result["tokens_used"] == 0
