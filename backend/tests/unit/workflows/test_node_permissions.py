"""Step-type denial provenance, distinct-kind evaluation and public error safety."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.requests import Request

from syntara.authz.audit.authorization_denied import AuthorizationDeniedHandler
from syntara.authz.engine import AuthzResult
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.core.constants import FieldLimits
from syntara.core.models import User
from syntara.workflows.error_handlers import node_kind_write_denied_handler
from syntara.workflows.exceptions import NodeKindWriteDeniedError
from syntara.workflows.models.node_permission import BlockedStepType, WorkflowWriteForbiddenProblemDetail
from syntara.workflows.node_kinds import NODE_KINDS
from syntara.workflows.node_permissions import check_node_kind_write_permission, node_kind_denial


def _result(*, allowed=False, denied=False, identifier="", policies=None) -> AuthzResult:
    return AuthzResult(allowed, denied, "", "", identifier, policies or [])


def test_forbidden_schema_preserves_required_error_fields():
    schema = WorkflowWriteForbiddenProblemDetail.model_json_schema()
    assert set(schema["required"]) == {"type", "title", "detail", "code", "retryable"}
    assert "blocked_step_types" in schema["properties"]


def test_long_step_type_denial_still_returns_a_problem_response():
    kind = "x" * (FieldLimits.DESCRIPTION_MAX_LENGTH + 1)
    blocked = BlockedStepType(kind=kind, label=kind, reason="no_matching_allow", project="payments")
    request = Request({"type": "http", "scheme": "https", "server": ("test", 443), "path": "/workflows", "headers": []})
    response = node_kind_write_denied_handler(request, NodeKindWriteDeniedError("save workflow", [blocked]))
    body = json.loads(response.body)
    assert response.status_code == 403
    assert len(body["detail"]) == FieldLimits.DESCRIPTION_MAX_LENGTH
    assert body["blocked_step_types"][0]["kind"] == kind


@pytest.mark.parametrize(("scope", "project"), [("any", None), ("project", "payments")])
def test_denial_uses_exact_effective_statement(scope, project):
    result = _result(
        denied=True,
        identifier="mixed/1@payments",
        policies=[
            {"name": "mixed/0", "policy_name": "mixed", "scope": "any"},
            {"name": "mixed/1@payments", "policy_name": "mixed", "scope": scope, "project": project},
        ],
    )
    denial = node_kind_denial("script", "payments", result)
    assert denial.policy == "mixed"
    assert denial.scope == scope
    assert denial.blocked.project == project
    assert denial.blocked.reason == "explicit_deny"


def test_missing_allow_has_no_policy_attribution():
    denial = node_kind_denial("script", "payments", _result())
    assert denial.policy is None
    assert denial.scope is None
    assert denial.blocked.reason == "no_matching_allow"
    assert denial.blocked.project == "payments"
    assert node_kind_denial("script", "payments", _result(allowed=True)) is None


@pytest.mark.parametrize("kind", sorted(NODE_KINDS))
async def test_every_kind_is_checked_once_and_audited_without_public_policy_details(kind):
    db = AsyncMock()
    db.scalar.return_value = "payments"
    user = User(id=uuid4(), username="author")
    definition = {"nodes": [{"type": kind}, {"type": kind}], "triggers": [{"type": kind}]}
    result = _result(
        denied=True,
        identifier="secret-policy/1",
        policies=[
            {"name": "secret-policy/1", "policy_name": "secret-policy", "scope": "project", "project": "payments"}
        ],
    )
    with (
        patch("syntara.workflows.node_permissions.authorize", AsyncMock(return_value=result)) as authorize,
        patch("syntara.workflows.node_permissions.AuditEventDispatcher.dispatch") as dispatch,
        pytest.raises(NodeKindWriteDeniedError) as raised,
    ):
        await check_node_kind_write_permission(
            db, MagicMock(), user, [definition, definition], project_id=uuid4(), operation="save workflow"
        )
    authorize.assert_awaited_once()
    assert authorize.call_args.args[2].resource_labels == {"kind": kind}
    event = dispatch.call_args.args[0]
    audit = AuthorizationDeniedHandler().handle(event)
    assert audit.structured_data.denied_by == "secret-policy"
    assert audit.structured_data.scope == "project"
    assert audit.structured_data.kind == kind
    assert audit.structured_data.project == "payments"
    request = Request({"type": "http", "scheme": "https", "server": ("test", 443), "path": "/workflows", "headers": []})
    response = node_kind_write_denied_handler(request, raised.value)
    assert response.status_code == 403
    body = json.loads(response.body)
    assert body["code"] == "NODE_KIND_WRITE_DENIED"
    assert body["blocked_step_types"][0]["kind"] == kind
    assert "save workflow" in body["detail"]
    assert "secret-policy" not in response.body.decode()
    assert "scope" not in body["blocked_step_types"][0]
    assert "policy" not in body["blocked_step_types"][0]


@pytest.mark.parametrize("evaluator", [None, MagicMock()])
async def test_evaluator_unavailable_fails_closed(evaluator):
    db = AsyncMock()
    db.scalar.return_value = "payments"
    user = User(id=uuid4(), username="author")
    with (
        patch("syntara.workflows.node_permissions.authorize", AsyncMock(side_effect=RuntimeError("offline"))),
        patch("syntara.workflows.node_permissions.AuditEventDispatcher.dispatch") as dispatch,
        pytest.raises(AuthorizationDeniedError, match="unavailable"),
    ):
        await check_node_kind_write_permission(
            db, evaluator, user, [{"nodes": [{"type": "script"}]}], project_id=uuid4(), operation="save workflow"
        )
    assert dispatch.call_args.args[0].context["reason"] == "evaluation_unavailable"
