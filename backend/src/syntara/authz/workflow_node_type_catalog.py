"""Load workflow node type ids from the v2 node type catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "workflows" / "v2" / "catalog" / "node_type_catalog.json"
)

NODE_TYPE_ACTIONS: tuple[str, ...] = ("read", "write", "execute")
WORKFLOW_NODE_TYPE_RESOURCE = "workflow_node_type"


@lru_cache(maxsize=1)
def load_node_type_catalog_entries() -> tuple[tuple[str, str], ...]:
    """Return (type_id, display_name) pairs from the node type catalog."""
    with _CATALOG_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    entries: list[tuple[str, str]] = []
    for entry in data.get("node_types", []):
        type_id = entry.get("type")
        if not type_id:
            continue
        display = entry.get("name") or type_id
        entries.append((str(type_id), str(display)))
    return tuple(entries)


def catalog_display_name(node_type: str) -> str:
    """Human-readable label for a catalog node type id."""
    for type_id, display in load_node_type_catalog_entries():
        if type_id == node_type:
            return display
    return node_type.replace("_", " ").title()
