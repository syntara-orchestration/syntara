"""Shared blocked-step results include exact attribution and implicit denies."""

from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AuthzResult
from syntara.authz.evaluator import AuthzEvaluator
from syntara.workflows.node_kinds import NODE_KINDS, node_kind_label
from syntara.workflows.node_permissions import blocked_step_type, denied_node_labels, evaluate_node_labels


def _result(
    *, allowed: bool = False, denied_by: str = "", effective: list[dict[str, Any]] | None = None
) -> AuthzResult:
    return AuthzResult(
        allowed=allowed,
        denied=bool(denied_by),
        matched_policy="",
        denial_reason="policy_deny" if denied_by else "",
        denied_by=denied_by,
        effective_policies=effective or [],
    )


@pytest.mark.parametrize(("scope", "project"), [("any", None), ("project", "payments")])
def test_exact_deny_statement_supplies_display_name_and_scope(scope: str, project: str | None) -> None:
    effective: list[dict[str, Any]] = [
        {"name": "mixed/0", "policy_name": "mixed", "effect": "allow", "scope": "any"},
        {"name": "mixed/1@other", "policy_name": "mixed", "effect": "deny", "scope": "project", "project": "other"},
        {"name": "mixed/1@payments", "policy_name": "mixed", "effect": "deny", "scope": scope, "project": project},
    ]
    result = _result(denied_by="mixed/1@payments", effective=effective)
    denial = blocked_step_type(result, kind="script", evaluated_project="payments")
    assert denial.model_dump() == {
        "kind": "script",
        "label": "Script",
        "reason": "explicit_deny",
        "policy": "mixed",
        "scope": scope,
        "project": project,
    }
    assert result.policy_name(result.denied_by) == "mixed"


@pytest.mark.parametrize("project", ["", "payments"])
def test_missing_allow_has_no_deny_attribution(project: str) -> None:
    denial = blocked_step_type(_result(), kind="script", evaluated_project=project)
    assert denial.reason == "no_matching_allow"
    assert denial.policy is None
    assert denial.scope is None
    assert denial.project == (project or None)


def test_allowed_result_cannot_be_reported_as_blocked() -> None:
    with pytest.raises(ValueError, match="allowed result"):
        blocked_step_type(_result(allowed=True), kind="script")


def test_explicit_deny_with_missing_provenance_is_an_error() -> None:
    with pytest.raises(ValueError, match="no matching effective"):
        blocked_step_type(_result(denied_by="missing/1"), kind="script")


def test_every_grantable_kind_has_a_catalog_label() -> None:
    assert all(node_kind_label(kind) for kind in NODE_KINDS)
    assert node_kind_label("script") == "Script"


@pytest.mark.asyncio
async def test_distinct_kinds_evaluate_once_with_principal_context(monkeypatch: pytest.MonkeyPatch) -> None:
    authorize = AsyncMock(return_value=_result(allowed=True))
    monkeypatch.setattr("syntara.workflows.node_permissions.authorize", authorize)
    script = frozenset({("kind", "script")})
    http = frozenset({("kind", "http_request")})
    user_id = uuid4()
    results = await evaluate_node_labels(
        AsyncMock(spec=AsyncSession),
        Mock(spec=AuthzEvaluator),
        user_id=user_id,
        action="write",
        label_sets=[script, http, script],
        project_name="payments",
        user_labels={"team": "ops"},
        user_metadata={"level": 2},
    )
    assert list(results) == [http, script]
    assert authorize.await_count == 2
    request = authorize.await_args_list[0].args[2]
    assert (request.user_id, request.resource_type, request.action) == (user_id, "step_type", "write")
    assert request.resource_labels == {"kind": "http_request"}
    assert request.resource_project == "payments"
    assert request.user_labels == {"team": "ops"}
    assert request.user_metadata == {"level": 2}
    assert request.check_any_project is False


@pytest.mark.asyncio
async def test_denied_labels_include_missing_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    authorize = AsyncMock(side_effect=[_result(allowed=True), _result()])
    monkeypatch.setattr("syntara.workflows.node_permissions.authorize", authorize)
    denied = await denied_node_labels(
        AsyncMock(spec=AsyncSession),
        Mock(spec=AuthzEvaluator),
        user_id=uuid4(),
        action="write",
        label_sets=[frozenset({("kind", "script")}), frozenset({("kind", "http_request")})],
        project_name="payments",
    )
    assert [entry.kind for entry in denied] == ["script"]
    assert denied[0].reason == "no_matching_allow"
    assert denied[0].project == "payments"


@pytest.mark.asyncio
async def test_unsupported_action_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported step_type action"):
        await evaluate_node_labels(
            AsyncMock(spec=AsyncSession), Mock(spec=AuthzEvaluator), user_id=uuid4(), action="execute", label_sets=[]
        )
