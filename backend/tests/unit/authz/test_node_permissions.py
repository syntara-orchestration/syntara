"""Tests for the Blocked step type contract built from AuthzResults."""

from typing import Any

import pytest

from syntara.authz.engine import AuthzResult
from syntara.workflows.node_kinds import NODE_KINDS, node_kind_display_label
from syntara.workflows.node_permissions import NodeKindDenial, blocked_step_type


def _result(
    *,
    allowed: bool = False,
    denied: bool = False,
    denied_by: str = "",
    effective: list[dict[str, Any]] | None = None,
) -> AuthzResult:
    """Build an AuthzResult by hand for contract-mapping tests."""
    return AuthzResult(
        allowed=allowed,
        denied=denied,
        matched_policy="",
        denial_reason="policy_deny" if denied else "",
        denied_by=denied_by,
        effective_policies=effective or [],
    )


def _deny_entry(
    name: str,
    *,
    policy_name: str | None = None,
    scope: str = "any",
    project: str | None = None,
    kind: str | None = "script",
) -> dict[str, Any]:
    """Build an effective-policy deny entry as the resolver expands it."""
    entry: dict[str, Any] = {
        "name": name,
        "policy_name": policy_name if policy_name is not None else name,
        "statement_index": 0,
        "effect": "deny",
        "actions": ["step_type:write"],
        "scope": scope,
    }
    if project is not None:
        entry["project"] = project
    if kind is not None:
        entry["conditions"] = {"resource_labels": {"kind": kind}}
    return entry


def test_explicit_global_deny_has_null_scope_and_project() -> None:
    """A global deny reports the policy name with null scope/project."""
    result = _result(denied=True, denied_by="no-scripts", effective=[_deny_entry("no-scripts")])
    denial = blocked_step_type(result, "script")
    assert denial.to_dict() == {
        "kind": "script",
        "label": "Script",
        "reason": "explicit_deny",
        "policy": "no-scripts",
        "scope": None,
        "project": None,
    }


def test_explicit_project_deny_reports_scope_and_project() -> None:
    """A project deny reports scope "project" and the denying project."""
    entry = _deny_entry("no-scripts-in-prod", scope="project", project="payments")
    result = _result(denied=True, denied_by="no-scripts-in-prod", effective=[entry])
    denial = blocked_step_type(result, "script", project="payments")
    assert denial.reason == "explicit_deny"
    assert denial.policy == "no-scripts-in-prod"
    assert denial.scope == "project"
    assert denial.project == "payments"


def test_multi_statement_policy_reports_original_name() -> None:
    """The per-statement identifier never appears as the display policy name."""
    entry = _deny_entry("mixed-policy/1", policy_name="mixed-policy")
    result = _result(denied=True, denied_by="mixed-policy/1", effective=[entry])
    denial = blocked_step_type(result, "http_request")
    assert denial.policy == "mixed-policy"
    assert "/1" not in denial.policy


def test_implicit_denial_reports_no_matching_allow() -> None:
    """allowed=False without a deny is blocked with null policy/scope."""
    result = _result(allowed=False, denied=False, denied_by="", effective=[])
    denial = blocked_step_type(result, "script", project="payments")
    assert denial.to_dict() == {
        "kind": "script",
        "label": "Script",
        "reason": "no_matching_allow",
        "policy": None,
        "scope": None,
        "project": "payments",
    }


def test_implicit_denial_without_project_reports_null_project() -> None:
    """No evaluated project means a null project in the contract."""
    result = _result(allowed=False, denied=False, denied_by="", effective=[])
    denial = blocked_step_type(result, "script")
    assert denial.project is None


def test_unresolvable_denied_by_falls_back_to_matching_deny() -> None:
    """A denied_by that matches no entry still resolves to a real deny."""
    entry = _deny_entry("real-deny")
    result = _result(denied=True, denied_by="ghost-policy", effective=[entry])
    denial = blocked_step_type(result, "script")
    assert denial.reason == "explicit_deny"
    assert denial.policy == "real-deny"


def test_multiple_denies_report_deterministic_first() -> None:
    """With two matching denies, the sorted-first name is reported."""
    entry_b = _deny_entry("b-policy")
    entry_a = _deny_entry("a-policy")
    result = _result(denied=True, denied_by="b-policy", effective=[entry_b, entry_a])
    # The engine's denied_by is authoritative (sorted first of the matches).
    denial = blocked_step_type(result, "script")
    assert denial.policy == "b-policy"


def test_multiple_denies_fallback_sorts_by_name() -> None:
    """The defensive fallback picks the deterministic first by identifier."""
    entry_b = _deny_entry("b-policy")
    entry_a = _deny_entry("a-policy")
    result = _result(denied=True, denied_by="unresolved", effective=[entry_b, entry_a])
    denial = blocked_step_type(result, "script")
    assert denial.policy == "a-policy"


def test_deny_for_other_kind_is_not_matched() -> None:
    """A deny whose kind condition targets another step type does not match."""
    entry = _deny_entry("no-approvals", kind="approval")
    result = _result(denied=True, denied_by="ghost", effective=[entry])
    denial = blocked_step_type(result, "script")
    assert denial.reason == "no_matching_allow"
    assert denial.policy is None


def test_blocked_step_type_rejects_allowed_result() -> None:
    """An allowed result has no denial to report."""
    result = _result(allowed=True)
    with pytest.raises(ValueError, match="allowed"):
        blocked_step_type(result, "script")


def test_every_grantable_kind_has_a_display_label() -> None:
    """The label map covers every grantable step type."""
    for kind in NODE_KINDS:
        label = node_kind_display_label(kind)
        assert label
        assert label == label.strip()
    assert node_kind_display_label("script") == "Script"
    assert node_kind_display_label("http_request") == "REST API"


def test_unknown_kind_falls_back_to_title_case() -> None:
    """An unmapped kind still gets a readable label."""
    assert node_kind_display_label("future_kind") == "Future Kind"


def test_node_kind_denial_is_frozen() -> None:
    """The contract value object is immutable."""
    denial = NodeKindDenial(kind="script", label="Script", reason="explicit_deny", policy="p", scope=None, project=None)
    with pytest.raises(AttributeError):
        denial.policy = "other"  # type: ignore[misc]
