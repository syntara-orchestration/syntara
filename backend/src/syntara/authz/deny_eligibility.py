"""Deny-effect eligibility: which resource:action pairs may carry ``effect: deny``.

Deny-effect custom policies were disabled in AAP-74620 because a deny
unconditionally overrides every allow in Rego, there is no superuser in
the engine, and a project admin can attach a policy to a role assigned to
the implicit ``authenticated`` group.  A deny covering ``policy:delete``
or ``role-assignment:revoke`` would therefore be unrecoverable through
the API.

The scoped control asked for by AAP-74620 is this allowlist: a deny may
only target the resource types — and, within them, the actions — listed
here, so the means to undo a deny can never themselves be denied.
Expanding deny to another resource:action pair means adding it here.
"""

from __future__ import annotations

from typing import Any

DENY_ELIGIBLE_RESOURCE_TYPES: frozenset[str] = frozenset({"step_type"})
"""Resource types that a ``deny``-effect statement may target."""


def deny_eligible_actions(resource_type: str) -> frozenset[str]:
    """Return the actions on *resource_type* that may carry ``effect: deny``."""
    if resource_type == "step_type":
        from syntara.workflows.node_kinds import NODE_ACTION_WRITE  # noqa: PLC0415

        return frozenset({NODE_ACTION_WRITE})
    return frozenset()


def find_ineligible_deny_actions(statements: list[dict[str, Any]]) -> list[str]:
    """Return action strings used with ``effect: deny`` that are not deny-eligible.

    Action strings are ``resource_type:action`` (``resource_type:*`` for the
    wildcard).  A deny statement whose actions contain nothing eligible is
    reported via its full action list, so an empty or entirely ineligible
    statement is still named in the error.
    """
    ineligible: list[str] = []
    for stmt in statements:
        if stmt.get("effect") != "deny":
            continue
        actions = stmt.get("actions", [])
        stmt_ineligible = [
            action_str
            for action_str in actions
            if action_str.partition(":")[2] not in deny_eligible_actions(action_str.partition(":")[0])
        ]
        if stmt_ineligible:
            ineligible.extend(stmt_ineligible)
        elif not actions:
            ineligible.append("<no actions>")
    return ineligible


def deny_not_allowed_message(ineligible: list[str]) -> str:
    """Build the error message for *ineligible* deny actions."""
    eligible = ", ".join(
        f"{resource_type}:{action}"
        for resource_type in sorted(DENY_ELIGIBLE_RESOURCE_TYPES)
        for action in sorted(deny_eligible_actions(resource_type))
    )
    return f"Deny effect is only allowed on '{eligible}'. Deny is not permitted on: {', '.join(ineligible)}"
