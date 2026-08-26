"""Normalize LLM ``response_metadata`` after LangChain chunk merges.

LangChain concatenates string scalars when merging stream chunks (content chunk
plus a trailing usage chunk). That yields doubled values such as ``stopstop``
and ``openai/gpt-3.5-turboopenai/gpt-3.5-turbo`` (AAP-87759, AAP-86784).
"""

from __future__ import annotations

from typing import Any


def collapse_concatenated_scalar(value: str) -> str:
    """Return ``value`` with exact self-concatenation removed.

    ``"stopstop"`` becomes ``"stop"``. Already-correct values are unchanged.
    Repeated doubling (four copies) is collapsed until the two halves differ.
    """
    collapsed = value
    while True:
        half, odd = divmod(len(collapsed), 2)
        if odd or not half:
            return collapsed
        if collapsed[:half] != collapsed[half:]:
            return collapsed
        collapsed = collapsed[:half]


def normalize_response_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Copy metadata and collapse doubled top-level string scalars.

    Nested dicts such as ``token_usage`` are copied as-is. Does not mutate
    the input mapping.
    """
    if not metadata:
        return {}
    normalized: dict[str, Any] = dict(metadata)
    for key, value in metadata.items():
        if isinstance(value, str):
            normalized[key] = collapse_concatenated_scalar(value)
    return normalized
