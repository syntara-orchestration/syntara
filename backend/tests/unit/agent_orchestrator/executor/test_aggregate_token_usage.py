"""Direct unit tests for aggregate_token_usage.

Review feedback questioned whether totals reflected only the last reasoning
flush. This helper sums every entry in llm_token_usage_log.
"""

from __future__ import annotations

from typing import Any

from syntara.agent_orchestrator.utils.token_usage import aggregate_token_usage


class TestAggregateTokenUsage:
    """Tests for aggregate_token_usage summing all LLM call log entries."""

    def test_sums_all_llm_call_entries(self) -> None:
        usage_log: list[dict[str, Any]] = [
            {"input_tokens": 100, "output_tokens": 40, "usage_details": {"prompt_tokens": 100}},
            {"input_tokens": 250, "output_tokens": 60, "usage_details": {"prompt_tokens": 250}},
            {"input_tokens": 50, "output_tokens": 10},
        ]
        prompt, completion, total, details = aggregate_token_usage(usage_log)
        assert prompt == 400
        assert completion == 110
        assert total == 510
        assert details is not None
        assert len(details) == 2  # entries without usage_details filtered

    def test_empty_log(self) -> None:
        prompt, completion, total, details = aggregate_token_usage([])
        assert prompt == 0
        assert completion == 0
        assert total == 0
        assert details is None
