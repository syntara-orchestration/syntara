"""Platform-wide node-kind kill switch (ANSTRAT-1750, design §6b).

Disabling a node kind is not a permission: it is a platform-wide switch that
removes the kind from the builder palette, rejects saving definitions that
still contain it, refuses to launch executions containing it and fails any
node of that kind that is about to start.  Export is never gated.

The list of disabled kinds lives in the ``workflows.disabled_node_kinds``
runtime setting (a JSON list of ``NodeType`` values) and is read through the
Redis-backed settings cache so API and worker processes agree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.workflows.node_kinds import NODE_KINDS, NodeKindCategory, get_node_kind

if TYPE_CHECKING:
    from collections.abc import Iterable

DISABLED_NODE_KINDS_SETTING_KEY = "workflows.disabled_node_kinds"
"""Runtime setting key holding the JSON list of disabled node kinds."""

NODE_KIND_DISABLED_ERROR_CODE = "node_kind_disabled"
"""Stable error code used by validation findings, launch refusals and failed nodes."""


def is_kind_switchable(kind: str) -> bool:
    """Return ``True`` if *kind* may be disabled.

    Flow-control kinds (including ``permission_check``) can never be
    disabled: doing so would break routing and denial handling itself.
    Unknown kinds are not switchable either.
    """
    info = get_node_kind(kind)
    return info is not None and info.category is not NodeKindCategory.FLOW_CONTROL


async def get_disabled_node_kinds() -> frozenset[str]:
    """Return the currently disabled node kinds (empty when the setting is unset)."""
    cache = get_runtime_settings()
    values = await cache.get_list(DISABLED_NODE_KINDS_SETTING_KEY, default=[])
    return frozenset(str(value) for value in values if isinstance(value, str) and is_kind_switchable(value))


def next_disabled_kinds(current: Iterable[str], kind: str, *, enabled: bool) -> list[str]:
    """Return the disabled-kinds list that results from flipping *kind*.

    The result is ordered by the node-kind registry (``NodeType`` declaration
    order) so the stored setting value is stable regardless of the order in
    which kinds were switched off.

    Args:
        current: The currently disabled kinds.
        kind: The kind being enabled or disabled.
        enabled: ``True`` to enable the kind (remove it), ``False`` to disable it.

    Returns:
        The new list of disabled kinds.

    """
    disabled = {value for value in current if is_kind_switchable(value)}
    if enabled:
        disabled.discard(kind)
    else:
        disabled.add(kind)
    return [info.kind for info in NODE_KINDS if info.kind in disabled]


def disabled_nodes_in_definition(
    definition: dict[str, Any] | None,
    disabled_kinds: frozenset[str],
) -> list[tuple[str, str]]:
    """Return ``(node_id, kind)`` for every node in *definition* whose kind is disabled."""
    if not definition or not disabled_kinds:
        return []
    found: list[tuple[str, str]] = []
    for node in definition.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        kind = node.get("type")
        if isinstance(kind, str) and kind in disabled_kinds:
            found.append((str(node.get("id", "")), kind))
    return found
