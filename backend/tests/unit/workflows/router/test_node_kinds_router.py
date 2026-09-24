"""Unit tests for the node-kind registry router (ANSTRAT-1750, slice 3).

The endpoint functions are exercised directly; the settings cache, the policy
evaluation and the settings write path are replaced with doubles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.dependencies import PermissionChecker
from syntara.core.syntara_router import _NoPermissionSentinel
from syntara.workflows import node_kinds_router as module
from syntara.workflows.exceptions import NodeKindNotFoundError, NodeKindNotSwitchableError
from syntara.workflows.node_kind_switch import DISABLED_NODE_KINDS_SETTING_KEY
from syntara.workflows.node_kinds import NODE_KINDS
from syntara.workflows.node_permissions import NodeKindDenial

if TYPE_CHECKING:
    from collections.abc import Iterator


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = "admin"
    user.labels = {}
    user.authz_metadata = {}
    return user


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

    def test_put_route_requires_setting_write(self) -> None:
        route = _route("PUT", "/node_kinds/{kind}/enabled")
        checkers = [dep for dep in _dependency_instances(route) if isinstance(dep, PermissionChecker)]
        assert len(checkers) == 1
        assert (checkers[0].resource_type, checkers[0].action) == ("setting", "write")
        assert route.operation_id == "set_node_kind_enabled"


class TestListNodeKinds:
    """GET /node_kinds reports the registry plus the caller's own verdicts."""

    async def _call(self, disabled: frozenset[str], denials: list[NodeKindDenial]) -> module.NodeKindsListResponse:
        with (
            patch.object(module, "get_disabled_node_kinds", AsyncMock(return_value=disabled)),
            patch.object(module, "denied_node_labels", AsyncMock(return_value=denials)),
        ):
            return await module.list_node_kinds(AsyncMock(), _user(), MagicMock())

    async def test_lists_every_registered_kind_in_registry_order(self) -> None:
        response = await self._call(frozenset(), [])
        assert [entry.kind for entry in response.resources] == [info.kind for info in NODE_KINDS]

    async def test_all_enabled_when_nothing_is_disabled(self) -> None:
        response = await self._call(frozenset(), [])
        assert all(entry.enabled for entry in response.resources)
        assert response.disabled_kinds == []

    async def test_disabled_kind_is_reported_and_echoed(self) -> None:
        response = await self._call(frozenset({"script"}), [])
        by_kind = {entry.kind: entry for entry in response.resources}
        assert by_kind["script"].enabled is False
        assert by_kind["http_request"].enabled is True
        assert response.disabled_kinds == ["script"]

    async def test_switchable_flag_follows_the_category(self) -> None:
        response = await self._call(frozenset(), [])
        by_kind = {entry.kind: entry for entry in response.resources}
        assert by_kind["script"].switchable is True
        assert by_kind["condition"].switchable is False

    async def test_deniable_actions_are_reported(self) -> None:
        response = await self._call(frozenset(), [])
        by_kind = {entry.kind: entry for entry in response.resources}
        assert by_kind["script"].deniable_actions == ["execute", "write"]
        assert by_kind["manual_trigger"].deniable_actions == ["write"]
        assert by_kind["condition"].deniable_actions == []

    async def test_authorization_attributes_are_reported(self) -> None:
        response = await self._call(frozenset(), [])
        by_kind = {entry.kind: entry for entry in response.resources}
        assert [attribute.model_dump() for attribute in by_kind["script"].attributes] == [
            {"name": "language", "allowed_values": ["bash", "python"]}
        ]
        assert by_kind["approval"].attributes == []

    async def test_can_write_is_true_by_default(self) -> None:
        response = await self._call(frozenset(), [])
        assert all(entry.can_write for entry in response.resources)

    async def test_can_write_is_false_when_the_evaluator_denies(self) -> None:
        denial = NodeKindDenial(kind="script", denied_by="no-scripts", reason="policy_deny")
        response = await self._call(frozenset(), [denial])
        by_kind = {entry.kind: entry for entry in response.resources}
        assert by_kind["script"].can_write is False
        assert by_kind["http_request"].can_write is True

    async def test_only_write_deniable_kinds_are_evaluated(self) -> None:
        """Flow control kinds can never be denied, so they are not sent to the engine."""
        denied = AsyncMock(return_value=[])
        with (
            patch.object(module, "get_disabled_node_kinds", AsyncMock(return_value=frozenset())),
            patch.object(module, "denied_node_labels", denied),
        ):
            await module.list_node_kinds(AsyncMock(), _user(), MagicMock())
        await_args = denied.await_args
        assert await_args is not None
        evaluated = {dict(label_set)["kind"] for label_set in await_args.kwargs["label_sets"]}
        assert "script" in evaluated
        assert "condition" not in evaluated
        assert await_args.kwargs["project_name"] == ""
        assert await_args.kwargs["action"] == "write"


class TestSetNodeKindEnabled:
    """PUT /node_kinds/{kind}/enabled flips the runtime setting."""

    async def _call(
        self,
        kind: str,
        *,
        enabled: bool,
        disabled: frozenset[str] = frozenset(),
    ) -> tuple[module.NodeKindRead, MagicMock, MagicMock]:
        service = MagicMock()
        service.update = AsyncMock()
        service_cls = MagicMock(return_value=service)
        dispatch = MagicMock()
        with (
            patch.object(module, "get_disabled_node_kinds", AsyncMock(return_value=disabled)),
            patch.object(module, "denied_node_labels", AsyncMock(return_value=[])),
            patch.object(module, "SettingsService", service_cls),
            patch.object(AuditEventDispatcher, "dispatch", dispatch),
        ):
            result = await module.set_node_kind_enabled(
                kind,
                module.NodeKindEnabledUpdate(enabled=enabled),
                AsyncMock(),
                _user(),
                MagicMock(),
            )
        return result, service, dispatch

    async def test_unknown_kind_raises_not_found(self) -> None:
        with pytest.raises(NodeKindNotFoundError):
            await self._call("not_a_kind", enabled=False)

    @pytest.mark.parametrize("kind", ["condition", "converge", "loop", "switch", "wait"])
    async def test_flow_control_kind_is_rejected(self, kind: str) -> None:
        with pytest.raises(NodeKindNotSwitchableError) as exc_info:
            await self._call(kind, enabled=False)
        assert "flow control" in str(exc_info.value)

    async def test_disabling_writes_through_the_settings_service(self) -> None:
        result, service, _ = await self._call("script", enabled=False)
        service.update.assert_awaited_once()
        assert service.update.await_args is not None
        kwargs = service.update.await_args.kwargs
        assert kwargs["key"] == DISABLED_NODE_KINDS_SETTING_KEY
        assert kwargs["value"] == ["script"]
        assert result.kind == "script"
        assert result.enabled is False

    async def test_enabling_removes_the_kind(self) -> None:
        result, service, _ = await self._call("script", enabled=True, disabled=frozenset({"script", "agentic"}))
        assert service.update.await_args is not None
        assert service.update.await_args.kwargs["value"] == ["agentic"]
        assert result.enabled is True

    async def test_no_op_does_not_write_or_audit(self) -> None:
        result, service, dispatch = await self._call("script", enabled=True, disabled=frozenset())
        service.update.assert_not_awaited()
        dispatch.assert_not_called()
        assert result.enabled is True

    async def test_audit_event_records_the_actor_and_intent(self) -> None:
        _, _, dispatch = await self._call("script", enabled=False)
        dispatch.assert_called_once()
        event = dispatch.call_args.args[0]
        assert event.kind == "script"
        assert event.enabled is False
        assert event.disabled_kinds == ["script"]
        assert event.actor_username == "admin"
        assert event.actor_id is not None
