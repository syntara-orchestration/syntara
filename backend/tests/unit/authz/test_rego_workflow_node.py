"""Step authoring uses ordinary label-aware Rego decisions."""

from typing import Any

import pytest

from syntara.authz.evaluator import evaluate_policy_input
from tests.unit.authz.conftest import allow_policy, build_opa_input, deny_policy, policies_for_role


@pytest.mark.parametrize("scope", ["any", "project"])
@pytest.mark.parametrize("project", ["payments", "other", ""])
@pytest.mark.parametrize("kind", ["script", "http_request"])
def test_deny_overrides_allow_only_in_matching_context(scope: str, project: str, kind: str) -> None:
    deny = deny_policy(
        "no-scripts", ["step_type:write"], scope=scope, conditions={"resource_labels": {"kind": "script"}}
    )
    if scope == "project":
        deny["project"] = "payments"
    result = evaluate_policy_input(
        build_opa_input(
            action="write",
            resource_type="step_type",
            resource_project=project,
            resource_labels={"kind": kind},
            effective_policies=[*policies_for_role("admin"), allow_policy("allow-all", ["step_type:write"]), deny],
        )
    )
    denied = kind == "script" and (scope == "any" or project == "payments")
    assert result["allow"] is not denied
    assert result["deny"] is denied
    assert result["denied_by"] == ("no-scripts" if denied else "")


@pytest.mark.parametrize("kind", ["script", "manual_trigger", "condition"])
def test_no_matching_allow_is_blocked_without_explicit_deny(kind: str) -> None:
    result = evaluate_policy_input(
        build_opa_input(action="write", resource_type="step_type", resource_labels={"kind": kind})
    )
    assert result["allow"] is False
    assert result["deny"] is False
    assert result["denied_by"] == ""


@pytest.mark.parametrize("reverse", [False, True])
def test_multiple_denies_choose_first_sorted_statement(*, reverse: bool) -> None:
    policies = [
        allow_policy("allow-all", ["step_type:write"]),
        deny_policy("z-deny", ["step_type:write"]),
        deny_policy("a-mixed/1@payments", ["step_type:write"], scope="project"),
    ]
    policies[-1]["project"] = "payments"
    if reverse:
        policies.reverse()
    result = evaluate_policy_input(
        build_opa_input(
            action="write", resource_type="step_type", resource_project="payments", effective_policies=policies
        )
    )
    assert result["denied_by"] == "a-mixed/1@payments"


@pytest.mark.parametrize("kind", ["script", "http_request"])
def test_deny_without_selector_covers_all_kinds(kind: str) -> None:
    result = evaluate_policy_input(
        build_opa_input(
            action="write",
            resource_type="step_type",
            resource_labels={"kind": kind},
            effective_policies=[
                allow_policy("allow-all", ["step_type:write"]),
                deny_policy("block-all", ["step_type:write"]),
            ],
        )
    )
    assert result["allow"] is False
    assert result["denied_by"] == "block-all"


@pytest.mark.parametrize(("kind", "expected"), [("script", False), ("http_request", True)])
def test_negative_kind_selector_uses_runtime_normalization(kind: str, *, expected: bool) -> None:
    policies: list[dict[str, Any]] = [
        allow_policy("allow-all", ["step_type:write"]),
        deny_policy("only-http", ["step_type:write"], conditions={"resource_labels_not": {"kind": "http_request"}}),
    ]
    result = evaluate_policy_input(
        build_opa_input(
            action="write", resource_type="step_type", resource_labels={"kind": kind}, effective_policies=policies
        )
    )
    assert result["allow"] is expected
