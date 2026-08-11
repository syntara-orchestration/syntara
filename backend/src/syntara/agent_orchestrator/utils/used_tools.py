"""Helpers for aggregating tool usage from agent message history."""

from __future__ import annotations

from collections import Counter
from typing import Any


def aggregate_used_tools(messages: list[Any] | None) -> list[dict[str, Any]]:
    """Build ``[{name, count}, ...]`` from AIMessage tool_calls in message history.

    Args:
        messages: LangGraph / LangChain message list (may be None/empty).

    Returns:
        Sorted list of tool name → usage count entries. Empty when no tool calls.

    """
    if not messages:
        return []

    counts: Counter[str] = Counter()
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            continue
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if isinstance(name, str) and name:
                counts[name] += 1

    return [{"name": name, "count": count} for name, count in sorted(counts.items())]
