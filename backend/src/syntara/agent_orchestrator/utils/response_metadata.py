"""Normalize LLM ``response_metadata`` after LangChain chunk merges.

LangChain concatenates string scalars when merging stream chunks (content chunk
plus a trailing usage chunk). That yields doubled or N-fold values such as
``stopstop`` / ``stopstopstop`` and repeated ``model_name`` (AAP-87759, AAP-86784).

Nested ``token_usage`` ints are *summed* by the same merge. When LangChain
``usage_metadata`` is present, persisted ``token_usage`` is rebuilt from it
instead of keeping the inflated merge.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Keys LangChain merge_dicts concatenates as strings on every chunk. Other
# top-level strings are copied unchanged so unrelated values are not collapsed.
_CONCATENATED_SCALAR_KEYS = frozenset(
    {
        "finish_reason",
        "model_name",
        "system_fingerprint",
        "service_tier",
        "ls_provider",
    }
)


def collapse_concatenated_scalar(value: str) -> str:
    """Return ``value`` with exact unit self-concatenation removed.

    ``"stopstop"`` and ``"stop" * 3`` become ``"stop"``. Already-correct values
    are unchanged. Uses the smallest prefix that tiles the whole string at
    least twice; odd multiplicities are handled, not only powers of two.
    """
    length = len(value)
    for unit_len in range(1, length // 2 + 1):
        if length % unit_len:
            continue
        unit = value[:unit_len]
        if unit * (length // unit_len) == value:
            return unit
    return value


def _token_usage_from_usage_metadata(usage: Mapping[str, Any]) -> dict[str, Any] | None:
    """Map LangChain ``usage_metadata`` onto OpenAI-style ``token_usage`` keys."""
    input_tokens = usage.get("input_tokens")
    if input_tokens is None:
        return None
    output_tokens = usage.get("output_tokens") or 0
    total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens
    rebuilt: dict[str, Any] = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    input_details = usage.get("input_token_details")
    if input_details is not None:
        rebuilt["prompt_tokens_details"] = input_details
    output_details = usage.get("output_token_details")
    if output_details is not None:
        rebuilt["completion_tokens_details"] = output_details
    return rebuilt


def normalize_response_metadata(
    metadata: dict[str, Any] | None,
    *,
    usage_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy metadata and collapse concatenated scalars on known keys.

    Nested dicts such as ``token_usage`` are copied as-is unless
    ``usage_metadata`` supplies ``input_tokens``, in which case counted
    ``token_usage`` fields are rebuilt from that source. Does not mutate
    the input mapping.
    """
    if not metadata:
        normalized: dict[str, Any] = {}
    else:
        normalized = dict(metadata)
        for key in _CONCATENATED_SCALAR_KEYS:
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = collapse_concatenated_scalar(value)

    if isinstance(usage_metadata, Mapping):
        rebuilt_usage = _token_usage_from_usage_metadata(usage_metadata)
        if rebuilt_usage is not None:
            existing = normalized.get("token_usage")
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(rebuilt_usage)
            normalized["token_usage"] = merged

    return normalized
