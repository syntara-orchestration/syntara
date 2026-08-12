"""Helpers for aggregating provider-reported LLM token usage."""

from typing import Any

from syntara.agent_orchestrator.token_manager.models import UsageDetails, UsageDetailsResult


def aggregate_token_usage(
    usage_log: list[dict[str, Any]],
) -> tuple[int, int, int, UsageDetailsResult]:
    """Aggregate token counts from LLM call entries and build usage_details.

    Maps extraction-layer field names (input_tokens, output_tokens) to
    DB-layer field names (prompt_tokens, completion_tokens).

    Args:
        usage_log: List of token usage entries from GenericAgent.

    Returns:
        Tuple of (prompt_tokens, completion_tokens, total_tokens, usage_details).
        usage_details is always a list of per-call details, or None if no
        provider metadata was captured.

    """
    prompt_tokens = sum(entry.get("input_tokens", 0) for entry in usage_log)
    completion_tokens = sum(entry.get("output_tokens", 0) for entry in usage_log)
    total_tokens = prompt_tokens + completion_tokens

    filtered: list[UsageDetails] = [
        entry["usage_details"] for entry in usage_log if entry.get("usage_details") is not None
    ]
    usage_details: UsageDetailsResult = filtered or None

    return prompt_tokens, completion_tokens, total_tokens, usage_details
