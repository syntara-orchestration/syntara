"""Unit tests for the step-type permissions router (ANSTRAT-2533 P6).

The endpoint function is exercised directly; the policy evaluation and the
project lookup are replaced with doubles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from pydantic_core import PydanticUndefined

from syntara.authz.engine import AuthzRequest, AuthzResult
from syntara.authz.exceptions import ProjectNotFoundError
from syntara.core.syntara_router import _NoPermissionSentinel
from syntara.workflows import node_kinds_router as module
from syntara.workflows.node_kinds_router import StepTypePermissionRead

if TYPE_CHECKING:
    from collections.abc import Iterator


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = "author"
    user.labels = {}
    user.authz_metadata = {}
    return user


def _result(
    *,
    allowed: bool = True,
    denied: bool = False,
    denied_by: str = "",
    effective_policies: list[dict[str, object]] | None = None,
) -> AuthzResult:
    return AuthzResult(
        allowed=allowed,
        denied=denied,
        matched_policy="",
        denial_reason="policy_deny" if denied else "",
        denied_by=denied_by,
        effective_policies=effective_policies or [],
    )


def _route(method: str, path: str) -> APIRoute:
    for route in module.router.routes:
        if isinstance(route, APIRoute) and route.path == path and method in (route.methods or ()):
            return route
    msg = f"route not found: {method} {path}"
    raise AssertionError(msg)


def _dependency_instances(route: APIRoute) -> Iterator[object]:
    for dep in route.dependencies:
        yield dep.dependency


class TestRouteWiring:
    """Route metadata and access control are declared as the standard requires."""

    def test_prefix_is_top_level(self) -> None:
        """The prefix is /node_kinds, not /workflows/node_kinds, to avoid shadowing."""
        assert module.router.prefix == "/node_kinds"

    def test_list_route_is_authenticated_only(self) -> None:
        route = _route("GET", "/node_kinds")
        assert any(isinstance(dep, _NoPermissionSentinel) for dep in _dependency_instances(route))
        assert route.operation_id == "list_node_kinds"

    def test_no_kill_switch_write_route(self) -> None:
        """The 1750-era PUT /{kind}/enabled kill switch is not ported (P6)."""
        paths = [route.path for route in module.router.routes if isinstance(route, APIRoute)]
        assert paths == ["/node_kinds"]

    def test_project_id_is_a_required_query_parameter(self) -> None:
        route = _route("GET", "/node_kinds")
        params = {param.alias: param for param in route.dependant.query_params}
        assert "project_id" in params
        assert params["project_id"].default is PydanticUndefined


class TestListNodeKinds:
    """GET /node_kinds reports the registry plus the caller's own verdicts."""

    async def _call(self, results: dict[str, AuthzResult]) -> list[StepTypePermissionRead]:
        user = _user()

        async def fake_authorize(_db: object, _evaluator: object, request: AuthzRequest) -> AuthzResult:
            return results.get(request.resource_labels["kind"], _result(allowed=True))

        with (
            patch.object(module, "authorize", fake_authorize),
            patch.object(module, "_project_name", AsyncMock(return_value="payments")),
        ):
            entries = await module.list_node_kinds(uuid4(), AsyncMock(), user, MagicMock())
        return [StepTypePermissionRead.model_validate(entry) for entry in entries]

    async def test_lists_every_grantable_kind_in_registry_order(self) -> None:
        response = await self._call({})
        assert [entry.kind for entry in response] == list(module._ALL_GRANTABLE_KINDS)
        assert "internal_activity" not in {entry.kind for entry in response}

    async def test_categories_follow_the_registry(self) -> None:
        response = await self._call({})
        by_kind = {entry.kind: entry for entry in response}
        assert by_kind["manual_trigger"].category == "trigger"
        assert by_kind["condition"].category == "flow_control"
        assert by_kind["script"].category == "action"

    async def test_allowed_kind_has_no_blocked_by(self) -> None:
        response = await self._call({"script": _result(allowed=True)})
        by_kind = {entry.kind: entry for entry in response}
        assert by_kind["script"].can_write is True
        assert by_kind["script"].blocked_by is None

    async def test_project_deny_reports_policy_scope_and_project(self) -> None:
        effective: list[dict[str, object]] = [
            {"name": "no-scripts/1@payments", "policy_name": "no-scripts", "scope": "project", "project": "payments"}
        ]
        script = _result(allowed=False, denied=True, denied_by="no-scripts/1@payments", effective_policies=effective)
        response = await self._call({"script": script})
        blocked = {entry.kind: entry for entry in response}["script"].blocked_by
        assert blocked is not None
        assert blocked.kind == "script"
        assert blocked.label == "Script"
        assert blocked.reason == "explicit_deny"
        assert blocked.policy == "no-scripts"
        assert blocked.scope == "project"
        assert blocked.project == "payments"

    async def test_global_deny_has_null_project(self) -> None:
        effective: list[dict[str, object]] = [{"name": "no-scripts", "policy_name": "no-scripts", "scope": "any"}]
        response = await self._call(
            {"script": _result(allowed=False, denied=True, denied_by="no-scripts", effective_policies=effective)}
        )
        blocked = {entry.kind: entry for entry in response}["script"].blocked_by
        assert blocked is not None
        assert blocked.reason == "explicit_deny"
        assert blocked.policy == "no-scripts"
        assert blocked.scope == "any"
        assert blocked.project is None

    async def test_missing_allow_reports_no_matching_allow(self) -> None:
        response = await self._call({"script": _result(allowed=False)})
        blocked = {entry.kind: entry for entry in response}["script"].blocked_by
        assert blocked is not None
        assert blocked.reason == "no_matching_allow"
        assert blocked.policy is None
        assert blocked.scope is None
        assert blocked.project == "payments"

    async def test_unknown_project_is_rejected(self) -> None:
        with patch.object(module, "_project_name", AsyncMock(side_effect=ProjectNotFoundError("nope"))):
            with pytest.raises(ProjectNotFoundError):
                await module.list_node_kinds(uuid4(), AsyncMock(), _user(), MagicMock())


class TestDenyScope:
    """The scope comes from the matching effective statement only."""

    def test_self_scope_is_normalized_to_project(self) -> None:
        result = _result(
            denied=True,
            denied_by="p/0",
            effective_policies=[{"name": "p/0", "policy_name": "p", "scope": "self", "project": "payments"}],
        )
        assert module._deny_scope(result, "p/0") == ("project", "payments")

    def test_unknown_identifier_reports_no_scope(self) -> None:
        result = _result(denied=True, denied_by="gone", effective_policies=[{"name": "other", "scope": "any"}])
        assert module._deny_scope(result, "gone") == (None, None)
