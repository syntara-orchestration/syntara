"""Step-type decision provenance used by the read-only editor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.authz.engine import AuthzResult
from syntara.authz.router import CanIRequest, can_i


@pytest.mark.parametrize(
    ("scope", "project", "check_any_project"),
    [("any", None, False), ("project", "payments", False), ("own", "payments", False), ("project", "payments", True)],
)
async def test_can_i_returns_exact_deny_statement_scope(
    scope: str, project: str | None, *, check_any_project: bool
) -> None:
    denied_by = "mixed/1@payments" if check_any_project else "mixed/1"
    result = AuthzResult(
        allowed=False,
        denied=True,
        matched_policy="",
        denial_reason="policy_deny",
        denied_by=denied_by,
        effective_policies=[
            {"name": "mixed/0", "policy_name": "mixed", "scope": "any"},
            {"name": "mixed/1", "policy_name": "mixed", "scope": "project", "project": "other"},
            {"name": denied_by, "policy_name": "mixed", "scope": scope, "project": project},
        ],
    )
    body = CanIRequest(
        action="write",
        resource_type="step_type",
        resource_project="" if check_any_project else "payments",
        check_any_project=check_any_project,
    )
    with patch("syntara.authz.router.authorize", new=AsyncMock(return_value=result)):
        response = await can_i(body, MagicMock(), AsyncMock(), AsyncMock())
    assert response.denied_by == "mixed"
    assert response.denied_scope == scope
    assert response.denied_project == (project or "")


@pytest.mark.parametrize("allowed", [True, False])
async def test_can_i_distinguishes_missing_allow_from_policy_deny(allowed):
    result = AuthzResult(
        allowed=allowed, denied=False, matched_policy="", denial_reason="", denied_by="", effective_policies=[]
    )
    with (
        patch("syntara.authz.router._resolve_project_input", new=AsyncMock(return_value="payments")),
        patch("syntara.authz.router.authorize", new=AsyncMock(return_value=result)),
    ):
        response = await can_i(
            CanIRequest(action="write", resource_type="step_type"), MagicMock(), AsyncMock(), AsyncMock()
        )
    assert response.denial_reason == ("" if allowed else "no_matching_allow")
    assert response.denied_by == ""
    assert response.denied_scope == ""
    assert response.denied_project == "payments"
