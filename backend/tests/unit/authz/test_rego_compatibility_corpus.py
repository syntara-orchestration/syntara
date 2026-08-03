"""Compatibility corpus for authz.rego decision semantics.

These cases freeze the observable decision contract for the in-process
regopy evaluator. The goal is to catch semantic drift in the Rego rule or
its result normalization, not just basic allow/deny regressions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest

from nexus.authz.evaluator import RegoEvaluator, evaluate_policy_input
from tests.unit.authz.conftest import allow_policy, build_opa_input, deny_policy


@dataclass(frozen=True)
class CompatibilityCase:
    """Single authz input with its expected public decision shape."""

    id: str
    authz_input: dict[str, Any]
    expected: dict[str, Any]


def _expected_result(
    *,
    allow: bool,
    deny: bool,
    matched_policy: str = "",
    denial_reason: str = "",
    denied_by: str = "",
    allowed_projects: list[str] | None = None,
) -> dict[str, Any]:
    """Build the exact result contract returned by the evaluator."""
    return {
        "allow": allow,
        "deny": deny,
        "matched_policy": matched_policy,
        "denial_reason": denial_reason,
        "denied_by": denied_by,
        "allowed_projects": sorted(allowed_projects or []),
    }


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize list ordering so exact equality stays stable."""
    normalized = dict(result)
    normalized["allowed_projects"] = sorted(normalized.get("allowed_projects", []))
    return normalized


COMPATIBILITY_CASES = [
    CompatibilityCase(
        id="allow-picks-first-sorted-policy-name",
        authz_input=build_opa_input(
            action="read",
            resource_type="workflow",
            effective_policies=[
                allow_policy("z-allow", ["workflow:read"]),
                allow_policy("a-allow", ["workflow:read"]),
            ],
        ),
        expected=_expected_result(
            allow=True,
            deny=False,
            matched_policy="a-allow",
            allowed_projects=["*"],
        ),
    ),
    CompatibilityCase(
        id="wildcard-action-matches-specific-request",
        authz_input=build_opa_input(
            action="delete",
            resource_type="workflow",
            effective_policies=[allow_policy("workflow-any", ["workflow:*"])],
        ),
        expected=_expected_result(
            allow=True,
            deny=False,
            matched_policy="workflow-any",
            allowed_projects=["*"],
        ),
    ),
    CompatibilityCase(
        id="deny-wins-and-picks-first-sorted-deny-policy",
        authz_input=build_opa_input(
            action="read",
            resource_type="workflow",
            resource_project="proj-a",
            effective_policies=[
                allow_policy("allow-read", ["workflow:read"], scope="project", project="proj-a"),
                deny_policy("block-z", ["workflow:read"]),
                deny_policy("block-a", ["workflow:read"]),
            ],
        ),
        expected=_expected_result(
            allow=False,
            deny=True,
            denial_reason="policy_deny",
            denied_by="block-a",
            allowed_projects=[],
        ),
    ),
    CompatibilityCase(
        id="project-scope-mismatch-still-reports-reachable-projects",
        authz_input=build_opa_input(
            action="read",
            resource_type="workflow",
            resource_project="proj-b",
            effective_policies=[
                allow_policy("proj-a-read", ["workflow:read"], scope="project", project="proj-a"),
            ],
        ),
        expected=_expected_result(
            allow=False,
            deny=False,
            allowed_projects=["proj-a"],
        ),
    ),
    CompatibilityCase(
        id="self-scope-user-match-allows",
        authz_input=build_opa_input(
            action="read",
            resource_type="user",
            resource_id="user-123",
            user_id="user-123",
            effective_policies=[allow_policy("user-self", ["user:read"], scope="self")],
        ),
        expected=_expected_result(
            allow=True,
            deny=False,
            matched_policy="user-self",
        ),
    ),
    CompatibilityCase(
        id="self-scope-empty-ids-known-quirk-still-allows",
        authz_input=build_opa_input(
            action="read",
            resource_type="user",
            resource_id="",
            user_id="",
            effective_policies=[allow_policy("user-self", ["user:read"], scope="self")],
        ),
        expected=_expected_result(
            allow=True,
            deny=False,
            matched_policy="user-self",
        ),
    ),
    CompatibilityCase(
        id="group-label-condition-matches-any-group",
        authz_input=build_opa_input(
            action="run",
            resource_type="execution",
            groups=[
                {"id": "basic", "name": "basic", "labels": {"tier": "basic"}},
                {"id": "premium", "name": "premium", "labels": {"tier": "premium"}},
            ],
            effective_policies=[
                allow_policy(
                    "premium-execution",
                    ["execution:run"],
                    conditions={"group_labels": {"tier": "premium"}},
                )
            ],
        ),
        expected=_expected_result(
            allow=True,
            deny=False,
            matched_policy="premium-execution",
            allowed_projects=["*"],
        ),
    ),
    CompatibilityCase(
        id="missing-user-label-satisfies-user-labels-not",
        authz_input=build_opa_input(
            action="read",
            resource_type="workflow",
            user_labels={},
            effective_policies=[
                allow_policy(
                    "not-suspended",
                    ["workflow:read"],
                    conditions={"user_labels_not": {"suspended": "true"}},
                )
            ],
        ),
        expected=_expected_result(
            allow=True,
            deny=False,
            matched_policy="not-suspended",
            allowed_projects=["*"],
        ),
    ),
    CompatibilityCase(
        id="unknown-effect-is-ignored",
        authz_input=build_opa_input(
            action="read",
            resource_type="workflow",
            effective_policies=[
                {
                    "name": "legacy-weird-effect",
                    "effect": "permit",
                    "actions": ["workflow:read"],
                    "scope": "any",
                }
            ],
        ),
        expected=_expected_result(
            allow=False,
            deny=False,
        ),
    ),
]


@pytest.fixture
async def rego_evaluator() -> AsyncGenerator[RegoEvaluator, None]:
    """Start the reusable evaluator used in runtime code paths."""
    evaluator = RegoEvaluator()
    evaluator.start()
    try:
        yield evaluator
    finally:
        await evaluator.stop()


@pytest.mark.parametrize("case", COMPATIBILITY_CASES, ids=lambda case: case.id)
def test_one_shot_evaluator_matches_compatibility_corpus(case: CompatibilityCase) -> None:
    """Freeze the public decision output for representative policy scenarios."""
    result = _normalize_result(evaluate_policy_input(case.authz_input))
    assert result == case.expected


@pytest.mark.asyncio
@pytest.mark.parametrize("case", COMPATIBILITY_CASES, ids=lambda case: case.id)
async def test_reusable_evaluator_matches_compatibility_corpus(
    case: CompatibilityCase,
    rego_evaluator: RegoEvaluator,
) -> None:
    """Ensure the long-lived runtime evaluator preserves the same semantics."""
    result = _normalize_result(rego_evaluator.evaluate(case.authz_input))
    assert result == case.expected
