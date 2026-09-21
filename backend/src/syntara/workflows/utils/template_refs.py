"""Template-reference path helpers.

Single source of truth for interpreting ``${node.field...}`` references
exactly as the runtime ``NamespaceResolver`` does, shared by restart
validation and activity code that must reason about which stored fields a
reference consumes.

Runtime semantics mirrored here (see ``namespace_resolver._lookup_path``):
dotted numeric segments address list indices (``${step.items.1}`` is index 1);
whole-namespace refs (``${step}``) address the entire subtree. Bracket syntax
(``${step.items[0]}``) is parsed defensively although the runtime resolver
does not substitute it.
"""

from __future__ import annotations

import re
from typing import Any

from syntara.workflows.utils.namespace_resolver import TEMPLATE_PATTERN


def parse_ref_segments(expression: str) -> tuple:
    """Split a template expression into path segments (names and indices)."""
    segments: list = []
    for part in expression.strip().split("."):
        if part.isdigit():
            segments.append(int(part))
            continue
        name, _, _ = part.partition("[")
        if name:
            segments.append(name)
        segments.extend(int(index) for index in re.findall(r"\[(\d+)\]", part))
    return tuple(segments)


def find_template_refs(value: Any) -> list[tuple[str, tuple]]:  # noqa: ANN401
    """Every ``(target node id, field path)`` template reference in a value."""
    found: list[tuple[str, tuple]] = []
    if isinstance(value, str):
        for match in TEMPLATE_PATTERN.finditer(value):
            segments = parse_ref_segments(match.group(1))
            if segments and isinstance(segments[0], str):
                found.append((segments[0], tuple(segments[1:])))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(find_template_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_template_refs(item))
    return found


def paths_overlap(first: tuple, second: tuple) -> bool:
    """Whether two field paths overlap (one is a prefix of the other)."""
    return first[: len(second)] == second or second[: len(first)] == first
