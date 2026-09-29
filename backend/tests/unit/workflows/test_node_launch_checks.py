"""Tests for the shared fail-fast workflow launch gate."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from syntara.authz.engine import AuthzResult
from syntara.service_accounts.models.service_account import ServiceAccountStatus
from syntara.workflows.node_launch_checks import check_workflow_launch

PRINCIPAL_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")


def _result(value: object | None) -> Any:  # noqa: ANN401
    result = MagicMock()
    result.first.return_value = value
    return result


def _db(*, user: object | None = None, service_account: object | None = None) -> Any:  # noqa: ANN401
    db = MagicMock()

    async def execute(statement: Any) -> Any:  # noqa: ANN401
        query = str(statement).lower()
        if "projects" in query:
            return _result("project-a")
        if "service_accounts" in query:
            return _result(service_account)
        return _result(user)

    db.exec = AsyncMock(side_effect=execute)
    return db


def _authz_result(*, allowed: bool, denied_by: str = "") -> AuthzResult:
    return AuthzResult(
        allowed=allowed,
        denied=not allowed,
        matched_policy="",
        denial_reason="policy_deny" if not allowed else "",
        denied_by=denied_by,
        effective_policies=[],
    )


def _definition() -> dict[str, Any]:
    return {
        "triggers": [{"id": "trigger", "type": "manual_trigger"}],
        "nodes": [
            {"id": "script-a", "type": "script"},
            {"id": "script-b", "type": "script"},
            {"id": "request", "type": "http_request"},
            {"id": "branch", "type": "condition"},
        ],
    }


@pytest.mark.asyncio
async def test_inactive_principal_is_rejected_before_any_policy_evaluation() -> None:
    user = SimpleNamespace(is_enabled=False, labels={}, authz_metadata={})
    evaluator = MagicMock()
    with (
        patch("syntara.workflows.node_launch_checks.authorize", new_callable=AsyncMock) as run_check,
        patch("syntara.workflows.node_launch_checks.AuditEventDispatcher.dispatch") as audit,
    ):
        rejection = await check_workflow_launch(
            _db(user=user),
            evaluator,
            definition=_definition(),
            principal_id=PRINCIPAL_ID,
            project_id=PROJECT_ID,
            trigger_type="scheduled_trigger",
        )

    assert rejection is not None
    assert rejection.reason == "principal_inactive"
    assert rejection.principal_id == PRINCIPAL_ID
    run_check.assert_not_awaited()
    audit.assert_called_once()
    assert audit.call_args.args[0].rejection is rejection


@pytest.mark.asyncio
async def test_execution_run_denial_stops_before_step_checks() -> None:
    user = SimpleNamespace(is_enabled=True, labels={}, authz_metadata={})
    with (
        patch(
            "syntara.workflows.node_launch_checks.authorize",
            AsyncMock(return_value=_authz_result(allowed=False, denied_by="no-run")),
        ),
        patch("syntara.workflows.node_permissions.authorize", new_callable=AsyncMock) as step_check,
        patch("syntara.workflows.node_launch_checks.AuditEventDispatcher.dispatch") as audit,
    ):
        rejection = await check_workflow_launch(
            _db(user=user),
            MagicMock(),
            definition=_definition(),
            principal_id=PRINCIPAL_ID,
            project_id=PROJECT_ID,
            trigger_type="manual_trigger",
        )

    assert rejection is not None
    assert rejection.reason == "execution_run_denied"
    assert rejection.denied_by == "no-run"
    step_check.assert_not_awaited()
    audit.assert_called_once()


@pytest.mark.asyncio
async def test_distinct_saved_step_types_are_checked_once_and_all_denied_steps_are_reported() -> None:
    user = SimpleNamespace(is_enabled=True, labels={"team": "ops"}, authz_metadata={})
    with (
        patch(
            "syntara.workflows.node_launch_checks.authorize",
            AsyncMock(return_value=_authz_result(allowed=True)),
        ),
        patch(
            "syntara.workflows.node_permissions.authorize",
            new_callable=AsyncMock,
            side_effect=lambda _db, _evaluator, request: _authz_result(
                allowed=request.resource_labels["kind"] not in {"script", "http_request"},
                denied_by=f"deny-{request.resource_labels['kind']}",
            ),
        ) as step_check,
        patch("syntara.workflows.node_launch_checks.AuditEventDispatcher.dispatch") as audit,
    ):
        rejection = await check_workflow_launch(
            _db(user=user),
            MagicMock(),
            definition=_definition(),
            principal_id=PRINCIPAL_ID,
            project_id=PROJECT_ID,
            trigger_type="manual_trigger",
        )

    assert rejection is not None
    assert rejection.reason == "step_type_denied"
    assert rejection.denied_steps == [
        {"node_id": "request", "kind": "http_request", "denied_by": "deny-http_request"},
        {"node_id": "script-a", "kind": "script", "denied_by": "deny-script"},
        {"node_id": "script-b", "kind": "script", "denied_by": "deny-script"},
    ]
    assert step_check.await_count == 4  # manual_trigger, script, http_request, condition
    assert len({call.args[2].resource_labels["kind"] for call in step_check.await_args_list}) == 4
    audit.assert_called_once()


@pytest.mark.asyncio
async def test_disabled_service_account_is_rejected() -> None:
    account = SimpleNamespace(status=ServiceAccountStatus.DISABLED, labels={})
    with patch("syntara.workflows.node_launch_checks.AuditEventDispatcher.dispatch"):
        rejection = await check_workflow_launch(
            _db(service_account=account),
            MagicMock(),
            definition=_definition(),
            principal_id=PRINCIPAL_ID,
            project_id=PROJECT_ID,
            trigger_type="webhook_trigger",
        )

    assert rejection is not None
    assert rejection.reason == "principal_inactive"
