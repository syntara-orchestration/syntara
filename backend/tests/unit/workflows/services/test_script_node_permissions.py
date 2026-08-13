"""Unit tests for script node permission checks in WorkflowService."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.workflows.services.workflow_service import WorkflowService


def _make_service(*, with_opa: bool = True) -> WorkflowService:
    session = AsyncMock()
    proj_result = MagicMock()
    proj_result.first.return_value = "test-project"
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


def _def_with_script() -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "nodes": [
            {
                "id": "n1",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo hello"},
            }
        ],
        "edges": [],
        "triggers": [],
    }


def _def_without_script() -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "nodes": [
            {
                "id": "n1",
                "type": "http_request",
                "parameters": {"url": "https://example.com"},
            }
        ],
        "edges": [],
        "triggers": [],
    }


class TestDefinitionContainsScriptNodes:
    def test_detects_script_node(self) -> None:
        assert WorkflowService._definition_contains_script_nodes(_def_with_script()) is True

    def test_no_script_node(self) -> None:
        assert WorkflowService._definition_contains_script_nodes(_def_without_script()) is False

    def test_empty_nodes(self) -> None:
        definition: dict[str, object] = {"schema_version": "2.0.0", "nodes": [], "edges": [], "triggers": []}
        assert WorkflowService._definition_contains_script_nodes(definition) is False


class TestCheckScriptEditPermission:
    @pytest.mark.asyncio
    async def test_no_script_nodes_skips_check(self) -> None:
        svc = _make_service()
        with patch("syntara.workflows.services.workflow_service.authorize") as mock_authorize:
            await svc._check_script_edit_permission(_def_without_script(), uuid4())
        mock_authorize.assert_not_called()

    @pytest.mark.asyncio
    async def test_script_nodes_allowed(self) -> None:
        svc = _make_service()
        allowed = MagicMock()
        allowed.allowed = True
        with patch("syntara.workflows.services.workflow_service.authorize", return_value=allowed):
            await svc._check_script_edit_permission(_def_with_script(), uuid4())

    @pytest.mark.asyncio
    async def test_script_nodes_denied_raises(self) -> None:
        svc = _make_service()
        denied = MagicMock()
        denied.allowed = False
        with patch("syntara.workflows.services.workflow_service.authorize", return_value=denied):
            with pytest.raises(AuthorizationDeniedError):
                await svc._check_script_edit_permission(_def_with_script(), uuid4())

    @pytest.mark.asyncio
    async def test_no_opa_client_raises(self) -> None:
        svc = _make_service(with_opa=False)
        with pytest.raises(AuthorizationDeniedError):
            await svc._check_script_edit_permission(_def_with_script(), uuid4())

    @pytest.mark.asyncio
    async def test_script_nodes_disabled_setting_raises(self) -> None:
        from syntara.workflows.exceptions import ScriptNodesDisabledError

        svc = _make_service()
        with patch(
            "syntara.workflows.services.workflow_service.get_runtime_settings"
        ) as mock_settings:
            cache = AsyncMock()
            cache.get_bool.return_value = False
            mock_settings.return_value = cache
            with pytest.raises(ScriptNodesDisabledError):
                await svc._check_script_edit_permission(_def_with_script(), uuid4())
