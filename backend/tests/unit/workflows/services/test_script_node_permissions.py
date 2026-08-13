"""Unit tests for script node permission checks in WorkflowService and ExecutionService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.workflows.services.execution_service import ExecutionService
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
    """Test script node detection helper."""

    def test_detects_script_node(self) -> None:
        assert WorkflowService._definition_contains_script_nodes(_def_with_script()) is True

    def test_no_script_node(self) -> None:
        assert WorkflowService._definition_contains_script_nodes(_def_without_script()) is False

    def test_empty_nodes(self) -> None:
        definition: dict[str, object] = {"schema_version": "2.0.0", "nodes": [], "edges": [], "triggers": []}
        assert WorkflowService._definition_contains_script_nodes(definition) is False


class TestCheckScriptEditPermission:
    """Test script:edit permission enforcement in workflow service."""

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
        with patch("syntara.workflows.services.workflow_service.get_runtime_settings") as mock_settings:
            cache = AsyncMock()
            cache.get_bool.return_value = False
            mock_settings.return_value = cache
            with pytest.raises(ScriptNodesDisabledError):
                await svc._check_script_edit_permission(_def_with_script(), uuid4())


class TestCheckScriptEditPermissionDiffBased:
    """Test diff-based script:edit check when previous_definition is provided."""

    @pytest.mark.asyncio
    async def test_unchanged_script_nodes_skips_check(self) -> None:
        """When script nodes haven't changed, no OPA call is made."""
        svc = _make_service()
        definition = _def_with_script()
        with patch("syntara.workflows.services.workflow_service.authorize") as mock_authorize:
            await svc._check_script_edit_permission(definition, uuid4(), previous_definition=definition)
        mock_authorize.assert_not_called()

    @pytest.mark.asyncio
    async def test_added_script_node_requires_permission(self) -> None:
        """Adding a script node to a previously script-free definition triggers the check."""
        svc = _make_service()
        denied = MagicMock()
        denied.allowed = False
        with patch("syntara.workflows.services.workflow_service.authorize", return_value=denied):
            with pytest.raises(AuthorizationDeniedError):
                await svc._check_script_edit_permission(
                    _def_with_script(), uuid4(), previous_definition=_def_without_script()
                )

    @pytest.mark.asyncio
    async def test_modified_script_code_requires_permission(self) -> None:
        """Changing script code in a node triggers the check."""
        svc = _make_service()
        old_def = _def_with_script()
        new_def = _def_with_script()
        new_def["nodes"][0]["parameters"]["code"] = "echo MODIFIED"  # type: ignore[index]
        denied = MagicMock()
        denied.allowed = False
        with patch("syntara.workflows.services.workflow_service.authorize", return_value=denied):
            with pytest.raises(AuthorizationDeniedError):
                await svc._check_script_edit_permission(new_def, uuid4(), previous_definition=old_def)

    @pytest.mark.asyncio
    async def test_no_previous_definition_is_presence_based(self) -> None:
        """Without previous_definition (new workflow), presence-based check applies."""
        svc = _make_service()
        denied = MagicMock()
        denied.allowed = False
        with patch("syntara.workflows.services.workflow_service.authorize", return_value=denied):
            with pytest.raises(AuthorizationDeniedError):
                await svc._check_script_edit_permission(_def_with_script(), uuid4())


class TestExtractScriptNodes:
    """Test the _extract_script_nodes helper."""

    def test_extracts_script_nodes(self) -> None:
        nodes = WorkflowService._extract_script_nodes(_def_with_script())
        assert len(nodes) == 1
        assert nodes[0]["type"] == "script"

    def test_no_script_nodes(self) -> None:
        nodes = WorkflowService._extract_script_nodes(_def_without_script())
        assert len(nodes) == 0

    def test_mixed_nodes(self) -> None:
        definition: dict[str, object] = {
            "nodes": [
                {"id": "n1", "type": "script", "parameters": {"code": "echo hi"}},
                {"id": "n2", "type": "http_request", "parameters": {}},
                {"id": "n3", "type": "script", "parameters": {"code": "echo bye"}},
            ]
        }
        nodes = WorkflowService._extract_script_nodes(definition)
        assert len(nodes) == 2


class TestCheckScriptExecutePermission:
    """Test script:execute permission enforcement in execution service."""

    @pytest.mark.asyncio
    async def test_no_script_nodes_skips_check(self) -> None:
        svc = _make_execution_service()
        with patch("syntara.workflows.services.execution_service.authorize") as mock_authorize:
            await svc._check_script_execute_permission(_def_without_script(), uuid4())
        mock_authorize.assert_not_called()

    @pytest.mark.asyncio
    async def test_script_nodes_allowed(self) -> None:
        svc = _make_execution_service()
        allowed = MagicMock()
        allowed.allowed = True
        with patch("syntara.workflows.services.execution_service.authorize", return_value=allowed):
            await svc._check_script_execute_permission(_def_with_script(), uuid4())

    @pytest.mark.asyncio
    async def test_script_nodes_denied_raises(self) -> None:
        svc = _make_execution_service()
        denied = MagicMock()
        denied.allowed = False
        with patch("syntara.workflows.services.execution_service.authorize", return_value=denied):
            with pytest.raises(AuthorizationDeniedError):
                await svc._check_script_execute_permission(_def_with_script(), uuid4())

    @pytest.mark.asyncio
    async def test_no_opa_client_raises(self) -> None:
        svc = _make_execution_service(with_opa=False)
        with pytest.raises(AuthorizationDeniedError):
            await svc._check_script_execute_permission(_def_with_script(), uuid4())

    @pytest.mark.asyncio
    async def test_script_nodes_disabled_setting_raises(self) -> None:
        from syntara.workflows.exceptions import ScriptNodesDisabledError

        svc = _make_execution_service()
        with patch("syntara.workflows.services.execution_service.get_runtime_settings") as mock_settings:
            cache = AsyncMock()
            cache.get_bool.return_value = False
            mock_settings.return_value = cache
            with pytest.raises(ScriptNodesDisabledError):
                await svc._check_script_execute_permission(_def_with_script(), uuid4())


def _make_execution_service(*, with_opa: bool = True) -> ExecutionService:
    """Create ExecutionService mock for testing."""
    session = AsyncMock()
    proj_result = MagicMock()
    proj_result.first.return_value = "test-project"
    session.exec.return_value = proj_result

    user = MagicMock()
    user.id = uuid4()
    user.labels = {}
    user.authz_metadata = {}

    svc = ExecutionService.__new__(ExecutionService)
    svc.session = session
    svc.user = user
    svc.opa_client = MagicMock(spec=AuthzEvaluator) if with_opa else None
    return svc
