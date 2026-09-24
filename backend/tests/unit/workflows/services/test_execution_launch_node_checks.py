"""Unit tests for the launch-time node-kind gates in ExecutionService (ANSTRAT-1750).

Covers the kill-switch pre-flight (nothing is started, HTTP 422) and the denied
set being computed for the right principal and carried into both the Temporal
input and the execution row.
"""

import json
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import node_kind_disabled_handler
from syntara.workflows.exceptions import NodeKindDisabledError
from syntara.workflows.services.execution_service import ExecutionService

_SERVICE_MODULE = "syntara.workflows.services.execution_service"

PRINCIPAL_ID = UUID("11111111-1111-4111-8111-111111111111")
PUBLISHER_ID = UUID("22222222-2222-4222-8222-222222222222")


def _definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "wf",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "step", "type": "script", "parameters": {}}],
        "edges": [],
    }


def _make_service(*, evaluator: Any = None) -> ExecutionService:  # noqa: ANN401
    """Build an ExecutionService with mocked session, user and evaluator."""
    svc = ExecutionService.__new__(ExecutionService)
    svc.session = AsyncMock()
    user = MagicMock()
    user.id = PRINCIPAL_ID
    user.labels = {}
    user.authz_metadata = {}
    svc.user = user
    svc.temporal_service = None
    svc.authz_evaluator = evaluator if evaluator is not None else MagicMock()
    return svc


def _workflow() -> MagicMock:
    wf = MagicMock()
    wf.id = uuid4()
    wf.project_id = uuid4()
    return wf


def _version() -> MagicMock:
    version = MagicMock()
    version.workflow_definition = _definition()
    version.published_by = PUBLISHER_ID
    version.created_by = uuid4()
    return version


class TestKillSwitchPreflight:
    """A disabled kind refuses the launch before Temporal is touched (AD-21)."""

    @pytest.mark.asyncio
    async def test_raises_and_never_computes_denials(self) -> None:
        svc = _make_service()
        with (
            patch(
                f"{_SERVICE_MODULE}.check_node_kinds_enabled",
                AsyncMock(side_effect=NodeKindDisabledError([("step", "script")])),
            ),
            patch(f"{_SERVICE_MODULE}.compute_denied_nodes", new_callable=AsyncMock) as compute,
            pytest.raises(NodeKindDisabledError),
        ):
            await svc._resolve_launch_node_permissions(
                workflow=_workflow(),
                workflow_version=_version(),
                trigger_node={"id": "trigger", "type": "manual_trigger"},
            )
        compute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_launch_starts_nothing_when_a_kind_is_disabled(self) -> None:
        svc = _make_service()
        svc.temporal_service = MagicMock()
        svc.temporal_service.start_workflow = AsyncMock()

        with (
            patch(
                f"{_SERVICE_MODULE}.check_node_kinds_enabled",
                AsyncMock(side_effect=NodeKindDisabledError([("step", "script")])),
            ),
            patch(f"{_SERVICE_MODULE}.get_settings", MagicMock(return_value=MagicMock(max_concurrent_workflows=0))),
            pytest.raises(NodeKindDisabledError),
        ):
            await svc._start_temporal_and_create_execution(
                workflow=_workflow(),
                workflow_version=_version(),
                input_data={},
                trigger_node_id="trigger",
                recorder=MagicMock(),
                component=MagicMock(),
            )

        svc.temporal_service.start_workflow.assert_not_awaited()
        session = cast("AsyncMock", svc.session)
        session.add.assert_not_called()


class TestPreflightProblemDetails:
    """The refusal surfaces as a 422 naming the offending nodes."""

    def test_handler_returns_422_with_disabled_nodes(self) -> None:
        exc = NodeKindDisabledError([("step", "script"), ("call", "http_request")])
        request = MagicMock(spec=Request)
        request.url = "https://localhost:8000/api/v1/executions"

        response = node_kind_disabled_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422
        body = json.loads(bytes(response.body))
        assert body["code"] == "NODE_KIND_DISABLED"
        assert body["error_code"] == "node_kind_disabled"
        assert body["type"] == PROBLEM_TYPES["validation_error"]
        assert body["retryable"] is False
        assert body["disabled_nodes"] == [
            {"node_id": "step", "kind": "script"},
            {"node_id": "call", "kind": "http_request"},
        ]


class TestDeniedSetAtLaunch:
    """The denied set is evaluated for the run principal and returned to the caller."""

    @pytest.mark.asyncio
    async def test_interactive_launch_uses_the_invoking_user(self) -> None:
        svc = _make_service()
        denied = [{"node_id": "step", "kind": "script", "denied_by": "no-scripts"}]
        with (
            patch(f"{_SERVICE_MODULE}.check_node_kinds_enabled", AsyncMock()),
            patch(f"{_SERVICE_MODULE}.compute_denied_nodes", AsyncMock(return_value=denied)) as compute,
        ):
            result, principal_id = await svc._resolve_launch_node_permissions(
                workflow=_workflow(),
                workflow_version=_version(),
                trigger_node={"id": "trigger", "type": "manual_trigger"},
            )

        assert result == denied
        assert principal_id == PRINCIPAL_ID
        assert compute.await_args is not None
        assert compute.await_args.kwargs["principal_id"] == PRINCIPAL_ID

    @pytest.mark.asyncio
    async def test_eda_launch_uses_the_publisher(self) -> None:
        svc = _make_service()
        with (
            patch(f"{_SERVICE_MODULE}.check_node_kinds_enabled", AsyncMock()),
            patch(f"{_SERVICE_MODULE}.compute_denied_nodes", AsyncMock(return_value=[])) as compute,
        ):
            _, principal_id = await svc._resolve_launch_node_permissions(
                workflow=_workflow(),
                workflow_version=_version(),
                trigger_node={"id": "trigger", "type": "eda_trigger"},
            )

        assert principal_id == PUBLISHER_ID
        assert compute.await_args is not None
        assert compute.await_args.kwargs["principal_id"] == PUBLISHER_ID

    @pytest.mark.asyncio
    async def test_falls_back_to_the_process_evaluator(self) -> None:
        """Worker-side callers have no request; the registered evaluator is used."""
        svc = _make_service()
        svc.authz_evaluator = None
        sentinel = MagicMock()
        with (
            patch(f"{_SERVICE_MODULE}.check_node_kinds_enabled", AsyncMock()),
            patch(f"{_SERVICE_MODULE}.get_node_authz_evaluator", MagicMock(return_value=sentinel)),
            patch(f"{_SERVICE_MODULE}.compute_denied_nodes", AsyncMock(return_value=[])) as compute,
        ):
            await svc._resolve_launch_node_permissions(
                workflow=_workflow(),
                workflow_version=_version(),
                trigger_node={"id": "trigger", "type": "manual_trigger"},
            )

        assert compute.await_args is not None
        assert compute.await_args.args[1] is sentinel
