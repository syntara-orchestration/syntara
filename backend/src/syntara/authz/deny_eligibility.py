"""Limit denies to step authoring so recovery permissions cannot be denied."""

from typing import Any

from syntara.workflows.node_kinds import NODE_ACTION_WRITE, NODE_RESOURCE_TYPE

DENY_ELIGIBLE_RESOURCE_TYPES = frozenset({NODE_RESOURCE_TYPE})
_DENY_ACTION = f"{NODE_RESOURCE_TYPE}:{NODE_ACTION_WRITE}"


def find_ineligible_deny_actions(statements: list[dict[str, Any]]) -> list[str]:
    """Return every deny action outside the exact step-type write contract."""
    return [
        action
        for statement in statements
        if statement.get("effect") == "deny"
        for action in statement.get("actions", [])
        if action != _DENY_ACTION
    ]


def validate_deny_statements(statements: list[dict[str, Any]]) -> str | None:
    """Share deny eligibility validation between API schemas and service callers."""
    invalid = find_ineligible_deny_actions(statements)
    if invalid:
        return f"Deny-effect statements may only target '{_DENY_ACTION}'; got: {', '.join(invalid)}"
    for statement in statements:
        if statement.get("effect") != "deny":
            continue
        if not statement.get("actions"):
            return f"Deny-effect statements require the action '{_DENY_ACTION}'"
        if statement.get("scope") not in {"any", "project"}:
            return "Deny-effect statements require scope 'any' or 'project'"
    return None
