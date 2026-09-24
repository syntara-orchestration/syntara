"""Unit tests for the save-time ``workflow_node:write`` check (ANSTRAT-1750).

Covers ``WorkflowService._check_node_kind_write_permission``,
``_baseline_definition``, the restore path, and the 403 problem-details
body produced by ``node_kind_write_denied_handler``.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.authz.evaluator import AuthzEvaluator
from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import node_kind_write_denied_handler
from syntara.workflows.exceptions import NodeKindWriteDeniedError
from syntara.workflows.node_permissions import NodeKindDenial
from syntara.workflows.services.workflow_service import WorkflowService

_SERVICE_MODULE = "syntara.workflows.services.workflow_service"


def _definition(*kinds: str) -> dict[str, Any]:
    """Build a definition dict whose nodes cover *kinds* (one node per kind)."""
    return {
        "schema_version": "2.0.0",
        "nodes": [{"id": f"n{index}", "type": kind} for index, kind in enumerate(kinds)],
        "edges": [],
        "triggers": [],
    }


def _make_service(*, with_opa: bool = True, project_name: str = "test-project") -> WorkflowService:
    """Build a WorkflowService with a mocked session, user and evaluator."""
    session: AsyncMock = AsyncMock()
    proj_result = MagicMock()
    proj_result.first.return_value = project_name
    session.exec.return_value = proj_result

    user = MagicMock()
    user.id = uuid4()
    user.labels = {}
    user.authz_metadata = {}

    svc = WorkflowService.__new__(WorkflowService)
    svc.session = session
    svc.user = user
    svc.opa_client = MagicMock(spec=AuthzEvaluator) if with_opa else None
    return svc


class TestCheckNodeKindWritePermission:
    """The introduce-only semantics of the save-time check."""

    @pytest.mark.asyncio
    async def test_kind_already_in_baseline_is_not_evaluated(self) -> None:
        """A kind present in the baseline is not introduced — no evaluation at all."""
        svc = _make_service()
        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock) as denied:
            await svc._check_node_kind_write_permission(
                _definition("http_request"),
                _definition("http_request"),
                uuid4(),
            )
        denied.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_second_node_of_same_kind_is_not_introduced(self) -> None:
        """Adding another node of a kind already in the baseline introduces nothing."""
        svc = _make_service()
        new_definition = _definition("http_request", "http_request", "script")
        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock, return_value=[]) as denied:
            await svc._check_node_kind_write_permission(
                new_definition,
                _definition("http_request", "script"),
                uuid4(),
            )
        denied.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_new_workflow_baseline_makes_every_kind_introduced(self) -> None:
        """A None baseline (new workflow, import, clone) introduces every kind."""
        svc = _make_service()
        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock, return_value=[]) as denied:
            await svc._check_node_kind_write_permission(
                _definition("http_request", "script"),
                None,
                uuid4(),
            )
        denied.assert_awaited_once()
        assert denied.await_args is not None
        assert denied.await_args.kwargs["label_sets"] == {
            frozenset({("kind", "http_request")}),
            frozenset({("kind", "script")}),
        }
        assert denied.await_args.kwargs["action"] == "write"
        assert denied.await_args.kwargs["user_id"] == svc.user.id
        assert denied.await_args.kwargs["project_name"] == "test-project"

    @pytest.mark.asyncio
    async def test_only_newly_added_kind_is_evaluated(self) -> None:
        """Editing a workflow only evaluates the kinds the edit adds."""
        svc = _make_service()
        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock, return_value=[]) as denied:
            await svc._check_node_kind_write_permission(
                _definition("script", "http_request"),
                _definition("script"),
                uuid4(),
            )
        assert denied.await_args is not None
        assert denied.await_args.kwargs["label_sets"] == {frozenset({("kind", "http_request")})}

    @pytest.mark.asyncio
    async def test_denied_kind_raises(self) -> None:
        """A denied introduced kind raises with the denial attached."""
        svc = _make_service()
        denial = NodeKindDenial(kind="http_request", denied_by="no-http", reason="policy_deny")
        with (
            patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock, return_value=[denial]),
            pytest.raises(NodeKindWriteDeniedError) as exc_info,
        ):
            await svc._check_node_kind_write_permission(_definition("http_request"), None, uuid4())
        assert exc_info.value.denials == [denial]
        assert "http_request" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_definition_skips_evaluation(self) -> None:
        """A definition with no nodes introduces nothing."""
        svc = _make_service()
        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock) as denied:
            await svc._check_node_kind_write_permission(_definition(), None, uuid4())
        denied.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_evaluator_skips_check(self) -> None:
        """Without an evaluator the check is skipped rather than failing the save."""
        svc = _make_service(with_opa=False)
        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock) as denied:
            await svc._check_node_kind_write_permission(_definition("http_request"), None, uuid4())
        denied.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_project_resolves_empty_project_name(self) -> None:
        """A workflow with no project evaluates with an empty project scope."""
        svc = _make_service()
        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock, return_value=[]) as denied:
            await svc._check_node_kind_write_permission(_definition("script"), None, None)
        assert denied.await_args is not None
        assert denied.await_args.kwargs["project_name"] == ""


class TestBaselineDefinition:
    """The baseline lookup returns the latest saved version's definition."""

    @staticmethod
    def _workflow() -> MagicMock:
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.current_version = 3
        return workflow

    @pytest.mark.asyncio
    async def test_returns_definition_of_current_version(self) -> None:
        svc = _make_service()
        workflow = self._workflow()
        stored = _definition("script")
        version = MagicMock()
        version.workflow_definition = stored
        svc._get_version_or_none = AsyncMock(return_value=version)  # type: ignore[method-assign]

        assert await svc._baseline_definition(workflow) == stored
        svc._get_version_or_none.assert_awaited_once_with(workflow.id, 3)

    @pytest.mark.asyncio
    async def test_returns_none_when_version_row_missing(self) -> None:
        svc = _make_service()
        svc._get_version_or_none = AsyncMock(return_value=None)  # type: ignore[method-assign]

        assert await svc._baseline_definition(self._workflow()) is None


class TestRestorePathCheck:
    """Restore re-introduces the kinds of the restored version."""

    @staticmethod
    def _prepare(svc: WorkflowService, project_id: UUID) -> tuple[MagicMock, MagicMock]:
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.is_builtin = False
        workflow.project_id = project_id
        workflow.current_version = 2

        target = MagicMock()
        target.workflow_definition = _definition("http_request")
        target.created_at = None
        target.name = "v1"

        current = MagicMock()
        current.workflow_definition = _definition("script")

        svc._get_workflow_for_update = AsyncMock(return_value=workflow)  # type: ignore[method-assign]
        svc._get_version_or_none = AsyncMock(side_effect=[target, current])  # type: ignore[method-assign]
        svc._create_version_record = AsyncMock()  # type: ignore[method-assign]
        return workflow, target

    @pytest.mark.asyncio
    async def test_restore_denied_kind_raises_before_writing(self) -> None:
        """A restore that re-introduces a denied kind fails before any version is created."""
        svc = _make_service()
        project_id = uuid4()
        self._prepare(svc, project_id)
        denial = NodeKindDenial(kind="http_request", denied_by="no-http", reason="policy_deny")

        with (
            patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock, return_value=[denial]),
            pytest.raises(NodeKindWriteDeniedError),
        ):
            await svc.restore_workflow_version(uuid4(), 1)

        svc._create_version_record.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_restore_allowed_kind_proceeds_to_version_creation(self) -> None:
        """An allowed restore reaches the version-creation step."""
        svc = _make_service()
        project_id = uuid4()
        self._prepare(svc, project_id)
        svc.get_workflow_with_version = AsyncMock(return_value=(MagicMock(), MagicMock()))  # type: ignore[method-assign]
        svc._create_version_record = AsyncMock(return_value=None)  # type: ignore[method-assign]

        with patch(f"{_SERVICE_MODULE}.denied_node_labels", new_callable=AsyncMock, return_value=[]):
            await svc.restore_workflow_version(uuid4(), 1)

        svc._create_version_record.assert_awaited_once()


class TestNodeKindWriteDeniedHandler:
    """The 403 problem-details body."""

    def test_problem_details_body(self) -> None:
        request = MagicMock(spec=Request)
        request.url = "https://api.example.com/api/v1/workflows"

        exc = NodeKindWriteDeniedError(
            [
                NodeKindDenial(kind="http_request", denied_by="no-http", reason="policy_deny"),
                NodeKindDenial(kind="script", denied_by="no-script", reason="policy_deny"),
            ]
        )
        response = node_kind_write_denied_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 403
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["forbidden"]
        assert data["title"] == "Forbidden"
        assert data["code"] == "NODE_KIND_WRITE_DENIED"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/api/v1/workflows"
        assert data["denied_kinds"] == [
            {
                "kind": "http_request",
                "labels": {"kind": "http_request"},
                "denied_by": "no-http",
                "reason": "policy_deny",
            },
            {
                "kind": "script",
                "labels": {"kind": "script"},
                "denied_by": "no-script",
                "reason": "policy_deny",
            },
        ]
