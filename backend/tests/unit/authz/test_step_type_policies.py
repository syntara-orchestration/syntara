"""Policy routes validate step types through the real policy service."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.dependencies import PermissionChecker
from syntara.authz.exceptions import DenyEffectNotAllowedError, InvalidResourceActionError
from syntara.authz.models.policy import Policy
from syntara.authz.policy_router import get_policy_service, router
from syntara.authz.resource_actions import get_resource_actions
from syntara.authz.router import get_resource_actions as resource_actions_endpoint
from syntara.authz.services.policy_service import PolicyService
from syntara.core.exception_registry import register_exceptions
from syntara.core.models import User
from syntara.core.router_discovery import iter_api_routes


@pytest.fixture
def policy_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, PolicyService, AsyncMock]]:
    """Bypass authentication and database I/O, retaining routing and validation."""
    session = AsyncMock(spec=AsyncSession)
    service = PolicyService(session, User(id=uuid4(), username="author", email="author@example.com"))
    policy = Policy(id=uuid4(), name="step-policy", statements=[], labels={})
    monkeypatch.setattr(service, "get_policy", AsyncMock(return_value=policy))
    monkeypatch.setattr(service, "_check_name_conflict", AsyncMock())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_policy_service] = lambda: service
    for route in iter_api_routes(app):
        for dependency in route.dependencies:
            if isinstance(dependency.dependency, PermissionChecker):
                app.dependency_overrides[dependency.dependency] = lambda: None
    app.state.resource_actions = get_resource_actions()
    app.get("/authz/resource_actions")(resource_actions_endpoint)
    register_exceptions(app)
    with TestClient(app) as client:
        yield client, service, session


def test_resource_actions_endpoint_lists_only_write(policy_client: tuple[TestClient, PolicyService, AsyncMock]) -> None:
    """The API exposes the explicit pair even without step-specific routes."""
    client, _, _ = policy_client
    response = client.get("/authz/resource_actions")
    assert response.status_code == 200
    assert response.json()["resource_actions"]["step_type"] == ["write"]


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT"])
@pytest.mark.parametrize("effect", ["allow", "deny"])
@pytest.mark.parametrize(
    ("conditions", "message"),
    [
        ({"resource_labels": {"kind": "scritp"}}, "Unknown step type 'scritp'"),
        ({"resource_labels_not": {"kind": "scritp"}}, "Unknown step type 'scritp'"),
        ({"resource_labels": {"kind": []}}, "Unknown step type"),
        ({"resource_labels": {"kind": "script", "language": "bash"}}, "Unsupported step type labels: language"),
        ({"resource_labels_not": {"model": "unapproved"}}, "Unsupported step type labels: model"),
        ({"resource_labels": ["script"]}, "must be an object"),
    ],
)
def test_invalid_step_type_returns_422(
    policy_client: tuple[TestClient, PolicyService, AsyncMock],
    method: str,
    effect: str,
    conditions: dict[str, Any],
    message: str,
) -> None:
    """Create and both update routes reject invalid labels without committing."""
    client, _, session = policy_client
    path = "/policies" if method == "POST" else f"/policies/{uuid4()}"
    response = client.request(
        method,
        path,
        json={
            "name": "step-policy",
            "statements": [
                {"effect": effect, "scope": "project", "actions": ["step_type:write"], "conditions": conditions}
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_RESOURCE_ACTION"
    assert message in response.json()["detail"]
    session.commit.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT"])
@pytest.mark.parametrize("effect", ["allow", "deny"])
@pytest.mark.parametrize("scope", ["any", "project"])
@pytest.mark.parametrize("conditions", [None, {"resource_labels": {"kind": "manual_trigger"}}])
def test_valid_step_policy_accepted(
    policy_client: tuple[TestClient, PolicyService, AsyncMock],
    method: str,
    effect: str,
    scope: str,
    conditions: dict[str, Any] | None,
) -> None:
    """A project-scoped kind or an unrestricted statement can be persisted."""
    client, _, session = policy_client
    statement = {"effect": effect, "scope": scope, "actions": ["step_type:write"], "conditions": conditions}
    response = client.request(
        method,
        "/policies" if method == "POST" else f"/policies/{uuid4()}",
        json={"name": "step-policy", "statements": [statement]},
    )
    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json()["statements"][0].get("conditions") == conditions
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_service_call_rejects_invalid_kind(
    policy_client: tuple[TestClient, PolicyService, AsyncMock],
) -> None:
    """Validation does not depend on the HTTP request schema."""
    _, service, session = policy_client
    with pytest.raises(InvalidResourceActionError, match="Unknown step type 'scritp'"):
        await service.create_policy(
            "invalid-step",
            [
                {
                    "effect": "allow",
                    "scope": "any",
                    "actions": ["step_type:write"],
                    "conditions": {"resource_labels": {"kind": "scritp"}},
                }
            ],
        )
    session.commit.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT"])
@pytest.mark.parametrize("action", ["step_type:*", "step_type:execute", "workflow:read", "policy:delete"])
def test_ineligible_deny_returns_422(
    policy_client: tuple[TestClient, PolicyService, AsyncMock], method: str, action: str
) -> None:
    client, _, session = policy_client
    response = client.request(
        method,
        "/policies" if method == "POST" else f"/policies/{uuid4()}",
        json={"name": "step-policy", "statements": [{"effect": "deny", "scope": "any", "actions": [action]}]},
    )
    assert response.status_code == 422
    assert action in str(response.json())
    session.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("update", [False, True])
@pytest.mark.parametrize(
    ("actions", "scope"), [(["policy:delete"], "any"), (["step_type:*"], "any"), (["step_type:write"], "self")]
)
async def test_direct_service_deny_validation_precedes_mutation(
    policy_client: tuple[TestClient, PolicyService, AsyncMock], actions: list[str], scope: str, *, update: bool
) -> None:
    _, service, session = policy_client
    policy = await service.get_policy(uuid4())
    statements = [{"effect": "deny", "actions": actions, "scope": scope}]
    with pytest.raises(DenyEffectNotAllowedError):
        if update:
            await service.update_policy(policy.id, name="renamed-policy", description="changed", statements=statements)
        else:
            await service.create_policy("invalid-deny", statements)
    assert policy.name == "step-policy"
    assert policy.statements == []
    session.commit.assert_not_called()
