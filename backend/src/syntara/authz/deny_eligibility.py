"""Which resource types may carry a deny-effect policy statement.

Deny-effect custom policies were disabled in AAP-74620 because a deny
unconditionally overrides every allow in Rego, there is no superuser in
the engine, and a project admin can attach a policy to a role assigned to
the implicit ``authenticated`` group.  A deny covering ``policy:delete``
or ``role-assignment:revoke`` would therefore be unrecoverable through
the API.

The scoped control asked for by AAP-74620 is this allowlist: a deny may
only target the resource types listed here, so the means to undo a deny
can never themselves be denied.  Expanding deny to another resource type
is adding its name to the set.
"""

from __future__ import annotations

from typing import Any

DENY_ELIGIBLE_RESOURCE_TYPES: frozenset[str] = frozenset({"workflow_node"})
"""Resource types that a ``deny``-effect statement may target."""


def find_ineligible_deny_actions(statements: list[dict[str, Any]]) -> list[str]:
    """Return the action strings of deny-effect statements that target ineligible resource types.

    Action strings are ``resource_type:action`` (``resource_type:*`` for the
    wildcard).  Only the resource type is inspected; the pair itself is
    validated separately against the resource-actions registry.
    """
    ineligible: list[str] = []
    for stmt in statements:
        if stmt.get("effect") != "deny":
            continue
        for action_str in stmt.get("actions", []):
            resource_type, _, _ = action_str.partition(":")
            if resource_type not in DENY_ELIGIBLE_RESOURCE_TYPES:
                ineligible.append(action_str)
    return ineligible


def deny_not_allowed_message(ineligible: list[str]) -> str:
    """Build the error message for *ineligible* deny actions."""
    eligible = ", ".join(sorted(DENY_ELIGIBLE_RESOURCE_TYPES))
    return f"Deny-effect statements may only target resource types [{eligible}]; got: {', '.join(ineligible)}"
