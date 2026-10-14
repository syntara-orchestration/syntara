"""Unit tests for Sub-workflow (Reference Mode) POC — ANSTRAT-2347.

Covers:
- SubWorkflowSetupActivity: depth limit, missing params, invalid workflow_id,
  trigger validation, idempotent retry
- OrchestratorWorkflow dispatch: _execute_sub_workflow_node calls setup activity
  then execute_child_workflow with correct args and ParentClosePolicy
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, uuid5

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.workflow import ParentClosePolicy

from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    _MAX_SUB_WORKFLOW_DEPTH,
    _SUB_WORKFLOW_NAMESPACE,
    SubWorkflowSetupActivity,
)
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityName,
    NodeType,
    SubWorkflowOutput,
)
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime

if TYPE_CHECKING:
    from collections.abc import Generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_setup_activity() -> SubWorkflowSetupActivity:
    session_factory = MagicMock()
    return SubWorkflowSetupActivity(session_factory=session_factory, task_queue="test-queue")


def _make_workflow_with_depth(depth: int = 0) -> OrchestratorWorkflow:
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.execution_id = "parent-exec-001"
    wf._created_by_user_id = str(uuid4())
    wf._sub_workflow_depth = depth
    wf._project_id = str(uuid4())
    wf.resolver = MagicMock()
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._cof_failed_nodes = set()
    wf._converge_branch_nodes = {}
    wf._has_unhandled_failure = False
    wf._cancelled_node = None
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    init_workflow_runtime(wf)
    return wf


def _make_setup_result(**overrides: object) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "execution_id": "child-exec-001",
        "temporal_workflow_id": "child-wf-child-exec-001",
        "workflow_definition": {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []},
        "trigger_node_id": "trigger_1",
        "input_data": {"key": "value"},
        "task_queue": "test-queue",
        "workflow_metadata": {"sub_workflow_depth": 1},
        "child_workflow_id": str(uuid4()),
        "child_workflow_name": "child-workflow",
        "child_workflow_version": 1,
    }
    defaults.update(overrides)
    return defaults


def _make_child_workflow_def(
    trigger_id: str = "trigger_1",
    trigger_type: str = NodeType.SUBWORKFLOW_TRIGGER,
) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": trigger_id, "type": trigger_type, "parameters": {}}],
        "nodes": [{"id": "node_a", "type": "script", "parameters": {}}],
        "edges": [{"from": trigger_id, "to": "node_a"}],
    }


def _mock_session_factory(*sessions: AsyncMock) -> MagicMock:
    """Build a session factory that yields a different session per `async with` call."""
    call_count = 0

    async def aenter(_self: object) -> AsyncMock:
        nonlocal call_count
        idx = min(call_count, len(sessions) - 1)
        call_count += 1
        return sessions[idx]

    ctx = MagicMock()
    ctx.__aenter__ = aenter
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


# ---------------------------------------------------------------------------
# SubWorkflowSetupActivity tests
# ---------------------------------------------------------------------------


class TestSetupActivityDepthLimit:
    """Depth-check guardrail in setup activity."""

    async def test_depth_at_max_raises_non_retryable(self) -> None:
        activity = _make_setup_activity()
        with pytest.raises(ApplicationError, match="nesting depth") as exc_info:
            await activity.run(
                parameters={"workflow_id": str(uuid4()), "trigger_node_id": "t1"},
                parent_execution_id="parent-001",
                parent_node_id="sub_wf_node",
                created_by_user_id=str(uuid4()),
                current_depth=_MAX_SUB_WORKFLOW_DEPTH,
            )
        assert exc_info.value.non_retryable

    async def test_depth_below_max_does_not_raise_depth_error(self) -> None:
        """Depth below max should pass the depth check (fails later on DB lookup)."""
        activity = _make_setup_activity()

        mock_session = AsyncMock()
        exec_result = MagicMock()
        exec_result.first.return_value = None
        mock_session.exec = AsyncMock(return_value=exec_result)

        activity._session_factory = _mock_session_factory(mock_session)

        with pytest.raises(ApplicationError, match="WorkflowNotPublishedError"):
            await activity.run(
                parameters={"workflow_id": str(uuid4()), "trigger_node_id": "t1"},
                parent_execution_id="parent-001",
                parent_node_id="sub_wf_node",
                created_by_user_id=str(uuid4()),
                current_depth=_MAX_SUB_WORKFLOW_DEPTH - 1,
            )


class TestSetupActivityValidation:
    """Parameter validation in setup activity."""

    async def test_missing_workflow_id_raises(self) -> None:
        activity = _make_setup_activity()
        with pytest.raises(ApplicationError, match="workflow_id") as exc_info:
            await activity.run(
                parameters={},
                parent_execution_id="parent-001",
                parent_node_id="sub_wf_node",
                created_by_user_id=str(uuid4()),
                current_depth=0,
            )
        assert exc_info.value.non_retryable

    async def test_missing_trigger_node_id_raises(self) -> None:
        activity = _make_setup_activity()
        with pytest.raises(ApplicationError, match="trigger_node_id") as exc_info:
            await activity.run(
                parameters={"workflow_id": str(uuid4())},
                parent_execution_id="parent-001",
                parent_node_id="sub_wf_node",
                created_by_user_id=str(uuid4()),
                current_depth=0,
            )
        assert exc_info.value.non_retryable

    async def test_invalid_workflow_id_format_raises(self) -> None:
        activity = _make_setup_activity()
        with pytest.raises(ApplicationError, match="Invalid workflow_id") as exc_info:
            await activity.run(
                parameters={"workflow_id": "not-a-uuid", "trigger_node_id": "t1"},
                parent_execution_id="parent-001",
                parent_node_id="sub_wf_node",
                created_by_user_id=str(uuid4()),
                current_depth=0,
            )
        assert exc_info.value.non_retryable


class TestSetupActivityTriggerValidation:
    """Trigger type and existence checks."""

    def test_wrong_trigger_type_raises(self) -> None:
        workflow_def = _make_child_workflow_def(trigger_type="manual_trigger")
        with pytest.raises(ApplicationError, match="InvalidTriggerType"):
            SubWorkflowSetupActivity._validate_trigger(workflow_def, "trigger_1")

    def test_missing_trigger_raises(self) -> None:
        workflow_def = _make_child_workflow_def()
        with pytest.raises(ApplicationError, match="TriggerNotFoundError"):
            SubWorkflowSetupActivity._validate_trigger(workflow_def, "nonexistent_trigger")

    def test_valid_subworkflow_trigger_passes(self) -> None:
        workflow_def = _make_child_workflow_def()
        SubWorkflowSetupActivity._validate_trigger(workflow_def, "trigger_1")


class TestSetupActivityIdempotency:
    """Idempotent retry returns existing execution without creating."""

    async def test_existing_execution_returns_without_creating(self) -> None:
        activity = _make_setup_activity()
        child_wf_id = uuid4()
        parent_exec_id = "parent-exec-001"
        parent_node_id = "sub_wf_node"
        user_id = str(uuid4())

        expected_child_exec_id = uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_exec_id}:{parent_node_id}")

        mock_workflow = MagicMock()
        mock_workflow.id = child_wf_id
        mock_workflow.name = "child-wf"
        mock_workflow.project_id = uuid4()
        mock_workflow.created_by = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = _make_child_workflow_def()

        mock_session_1 = AsyncMock()
        exec_result = MagicMock()
        exec_result.first.return_value = (mock_workflow, mock_version)
        mock_session_1.exec = AsyncMock(return_value=exec_result)

        mock_session_2 = AsyncMock()
        mock_session_2.get = AsyncMock(return_value=MagicMock())

        activity._session_factory = _mock_session_factory(mock_session_1, mock_session_2)

        with patch(
            "syntara.workflows.utils.workflow_metadata.resolve_user_display_name",
            return_value="Author",
        ):
            result = await activity.run(
                parameters={"workflow_id": str(child_wf_id), "trigger_node_id": "trigger_1"},
                parent_execution_id=parent_exec_id,
                parent_node_id=parent_node_id,
                created_by_user_id=user_id,
                current_depth=0,
            )

        assert result["execution_id"] == str(expected_child_exec_id)
        mock_session_2.add.assert_not_called()
        mock_session_2.commit.assert_not_called()


class TestSetupActivityExecution:
    """Happy-path: creates child execution and returns launch data."""

    async def test_creates_execution_and_returns_launch_data(self) -> None:
        activity = _make_setup_activity()
        child_wf_id = uuid4()
        parent_exec_id = "parent-exec-001"
        parent_node_id = "sub_wf_node"
        user_id = str(uuid4())

        mock_workflow = MagicMock()
        mock_workflow.id = child_wf_id
        mock_workflow.name = "child-wf"
        mock_workflow.project_id = uuid4()
        mock_workflow.created_by = uuid4()

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 2
        mock_version.workflow_definition = _make_child_workflow_def()

        mock_session_1 = AsyncMock()
        exec_result = MagicMock()
        exec_result.first.return_value = (mock_workflow, mock_version)
        mock_session_1.exec = AsyncMock(return_value=exec_result)

        mock_session_2 = AsyncMock()
        mock_session_2.get = AsyncMock(return_value=None)

        activity._session_factory = _mock_session_factory(mock_session_1, mock_session_2)

        with patch(
            "syntara.workflows.utils.workflow_metadata.resolve_user_display_name",
            return_value="Author",
        ):
            result = await activity.run(
                parameters={
                    "workflow_id": str(child_wf_id),
                    "trigger_node_id": "trigger_1",
                    "input_mapping": {"x": 1},
                },
                parent_execution_id=parent_exec_id,
                parent_node_id=parent_node_id,
                created_by_user_id=user_id,
                current_depth=0,
            )

        assert result["trigger_node_id"] == "trigger_1"
        assert result["input_data"] == {"x": 1}
        assert result["task_queue"] == "test-queue"
        assert result["child_workflow_name"] == "child-wf"
        assert result["child_workflow_version"] == 2
        assert result["workflow_metadata"]["sub_workflow_depth"] == 1
        mock_session_2.add.assert_called_once()
        mock_session_2.commit.assert_called_once()


class TestSetupActivityDeterministicId:
    """uuid5 child execution ID is stable across retries."""

    def test_child_execution_id_is_deterministic(self) -> None:
        parent_exec_id = "parent-exec-001"
        parent_node_id = "sub_wf_node"
        expected = uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_exec_id}:{parent_node_id}")
        same = uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_exec_id}:{parent_node_id}")
        assert expected == same

    def test_different_nodes_produce_different_ids(self) -> None:
        parent_exec_id = "parent-exec-001"
        id_a = uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_exec_id}:node_a")
        id_b = uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_exec_id}:node_b")
        assert id_a != id_b


class TestSetupActivityRegistration:
    """Temporal activity decorator matches enum name."""

    def test_activity_name_matches_enum(self) -> None:
        activity = _make_setup_activity()
        defn = getattr(activity.run, "__temporal_activity_definition")
        assert defn.name == ActivityName.SUB_WORKFLOW


# ---------------------------------------------------------------------------
# OrchestratorWorkflow dispatch tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module to avoid sandbox errors."""
    mock_logger = MagicMock()
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf,
        patch("syntara.workflows.workflow_engine.converge_mixin.workflow", mock_wf),
    ):
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        yield mock_wf


@pytest.mark.usefixtures("_mock_temporal_workflow")
class TestSubWorkflowDispatch:
    """OrchestratorWorkflow._execute_sub_workflow_node integration."""

    async def test_dispatch_routes_sub_workflow_node(self) -> None:
        wf = _make_workflow_with_depth(0)
        setup_result = _make_setup_result()

        with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value=setup_result)
            mock_wf.execute_child_workflow = AsyncMock(return_value={"status": "completed"})

            node = ActivityNode(
                node_id="sub_wf_1",
                node_type=NodeType.SUB_WORKFLOW,
                parameters={"workflow_id": str(uuid4()), "trigger_node_id": "trigger_1"},
            )

            result = await wf._execute_sub_workflow_node(node, node.parameters)

        assert result["output"]["child_execution_id"] == setup_result["execution_id"]
        assert result["output"]["child_status"] == "completed"

    async def test_execute_activity_args(self) -> None:
        wf = _make_workflow_with_depth(2)
        setup_result = _make_setup_result()

        with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value=setup_result)
            mock_wf.execute_child_workflow = AsyncMock(return_value={"status": "completed"})

            node = ActivityNode(
                node_id="sub_wf_1",
                node_type=NodeType.SUB_WORKFLOW,
                parameters={"workflow_id": "wf-123", "trigger_node_id": "t1"},
            )

            await wf._execute_sub_workflow_node(node, node.parameters)

            call_kwargs = mock_wf.execute_activity.call_args
            assert call_kwargs[0][0] == ActivityName.SUB_WORKFLOW
            args = call_kwargs[1]["args"]
            assert args[0] == node.parameters
            assert args[1] == wf.execution_id
            assert args[2] == "sub_wf_1"
            assert args[3] == wf._created_by_user_id
            assert args[4] == 2

    async def test_child_workflow_args(self) -> None:
        wf = _make_workflow_with_depth(0)
        setup_result = _make_setup_result()

        with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value=setup_result)
            mock_wf.execute_child_workflow = AsyncMock(return_value={"status": "completed"})

            node = ActivityNode(
                node_id="sub_wf_1",
                node_type=NodeType.SUB_WORKFLOW,
                parameters={},
            )

            await wf._execute_sub_workflow_node(node, {})

            child_call = mock_wf.execute_child_workflow.call_args
            assert child_call[0][0] == "orchestrator_workflow"
            positional_args = child_call[1]["args"]
            assert positional_args[0] == setup_result["workflow_definition"]
            assert positional_args[1] == setup_result["execution_id"]
            assert positional_args[2] == setup_result["trigger_node_id"]
            assert positional_args[3] == setup_result["input_data"]
            assert positional_args[4] is False
            assert positional_args[8] == setup_result["workflow_metadata"]
            assert child_call[1]["id"] == setup_result["temporal_workflow_id"]
            assert child_call[1]["task_queue"] == setup_result["task_queue"]
            assert child_call[1]["parent_close_policy"] == ParentClosePolicy.REQUEST_CANCEL

    async def test_child_non_dict_result(self) -> None:
        wf = _make_workflow_with_depth(0)
        setup_result = _make_setup_result()

        with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value=setup_result)
            mock_wf.execute_child_workflow = AsyncMock(return_value="unexpected")

            node = ActivityNode(
                node_id="sub_wf_1",
                node_type=NodeType.SUB_WORKFLOW,
                parameters={},
            )

            result = await wf._execute_sub_workflow_node(node, {})

        assert result["output"]["child_status"] == "unknown"


# ---------------------------------------------------------------------------
# Model / enum registration tests
# ---------------------------------------------------------------------------


class TestSubWorkflowModels:
    """Enum, output model, and settings registration."""

    def test_node_type_enum_exists(self) -> None:
        assert NodeType.SUB_WORKFLOW == "sub_workflow"

    def test_activity_name_enum_exists(self) -> None:
        assert ActivityName.SUB_WORKFLOW == "setup_sub_workflow_execution"

    def test_output_model_registered(self) -> None:
        from syntara.workflows.workflow_engine.models.workflow_definition import NODE_OUTPUT_MODELS

        assert NodeType.SUB_WORKFLOW in NODE_OUTPUT_MODELS
        assert NODE_OUTPUT_MODELS[NodeType.SUB_WORKFLOW] is SubWorkflowOutput

    def test_output_model_fields(self) -> None:
        output = SubWorkflowOutput()
        assert output.child_execution_id is None
        assert output.child_workflow_id is None
        assert output.child_status is None

    def test_node_settings_class_registered(self) -> None:
        from syntara.workflows.workflow_engine.graph import _NODE_SETTINGS_CLASS
        from syntara.workflows.workflow_engine.models.workflow_definition import NodeSettingsNoRetry

        assert NodeType.SUB_WORKFLOW in _NODE_SETTINGS_CLASS
        assert _NODE_SETTINGS_CLASS[NodeType.SUB_WORKFLOW] is NodeSettingsNoRetry


class TestDepthInitialization:
    """sub_workflow_depth read from workflow_metadata during state init."""

    def test_depth_from_workflow_metadata(self) -> None:
        wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
        wf._initialize_state(
            execution_id="exec-1",
            workflow_metadata={"sub_workflow_depth": 5, "workflow_context": {}},
        )
        assert wf._sub_workflow_depth == 5

    def test_depth_defaults_to_zero(self) -> None:
        wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
        wf._initialize_state(execution_id="exec-1", workflow_metadata={})
        assert wf._sub_workflow_depth == 0

    def test_depth_non_int_defaults_to_zero(self) -> None:
        wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
        wf._initialize_state(
            execution_id="exec-1",
            workflow_metadata={"sub_workflow_depth": "invalid"},
        )
        assert wf._sub_workflow_depth == 0

    def test_no_metadata_defaults_to_zero(self) -> None:
        wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
        wf._initialize_state(execution_id="exec-1")
        assert wf._sub_workflow_depth == 0
