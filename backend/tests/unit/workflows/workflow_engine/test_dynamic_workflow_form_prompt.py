"""Unit tests for OrchestratorWorkflow form_prompt context preparation methods.

Tests cover:
- _prepare_form_prompt_args: assembling the full argument list for create_form_prompt_activity
- _execute_form_prompt_node: dispatch routing, timeout handling, and fallback behavior
- _expire_form_prompts, _cancel_form_prompts: cleanup operations
- _fail_detached_form_prompt_activity: Temporal activity resolution
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.exceptions import TimeoutError as TemporalTimeoutError

from syntara.core.exceptions import SafeValueError
from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime

_FORM_DEFINITION_ARG = 3
_TIMEOUT_AT_ARG = 4
_RESPONDER_USER_IDS_ARG = 5
_RESPONDER_GROUP_IDS_ARG = 6
_LOOP_PATH_ARG = 8
_TEMPORAL_ID_ARG = 9
_MESSAGE_ARG = 10
_SUBMIT_LABEL_ARG = 11
_SUCCESS_MESSAGE_ARG = 12
_TIMEZONE_ARG = 13
_CSS_OVERRIDE_ARG = 14
_NEW_FORM_PROMPT_ARG_COUNT = 15


@pytest.fixture(autouse=True)
def _mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module."""
    mock_logger = MagicMock()
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf,
        patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow", mock_wf),
    ):
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id", run_id="test-run-id")
        mock_wf.now.return_value = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
        yield mock_wf


def _make_workflow(
    execution_id: str = "exec-123",
    resolver: NamespaceResolver | None = None,
) -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with initialized state, bypassing __init__."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.execution_id = execution_id
    wf._project_id = "00000000-0000-0000-0000-000000000001"
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf.resolver = resolver if resolver is not None else NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._converge_branch_nodes = {}
    wf._secret_values = set()
    wf._runtime_settings = {}
    init_workflow_runtime(wf)
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    return wf


def _build_form_prompt_graph(*, with_predecessor: bool = True, with_successor: bool = True) -> WorkflowGraph:
    """Build a graph with a form_prompt node.

    Structure: trigger -> [scan ->] form_prompt -> [process]
    """
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node(
        "form1",
        {
            "id": "form1",
            "type": "form_prompt",
            "name": "Data Collection",
            "parameters": {},
        },
    )

    if with_predecessor:
        backend.add_node(
            "scan",
            {"id": "scan", "type": "script", "name": "Scan Data", "parameters": {}},
        )
        backend.add_edge("trigger", "scan", None)
        backend.add_edge("scan", "form1", None)
    else:
        backend.add_edge("trigger", "form1", None)

    if with_successor:
        backend.add_node(
            "process",
            {"id": "process", "type": "script", "name": "Process Data", "parameters": {}},
        )
        backend.add_edge("form1", "process", {"from_port": "submitted"})

    graph = WorkflowGraph(backend)
    graph.metadata = {"name": "Data Pipeline"}
    return graph


class TestPrepareFormPromptArgs:
    """Tests for _prepare_form_prompt_args method."""

    @pytest.mark.asyncio
    async def test_basic_form_prompt_args(self) -> None:
        """Returns a 16-element arg list with all required fields."""
        resolver = NamespaceResolver()
        resolver.set_namespace("trigger", {"source": "api"})
        wf = _make_workflow(execution_id="exec-456", resolver=resolver)
        graph = _build_form_prompt_graph()
        node = ActivityNode("form1", "form_prompt", {}, name="Data Collection")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, node.parameters)

        assert len(args) == _NEW_FORM_PROMPT_ARG_COUNT
        assert args[0] == "exec-456"  # execution_id
        assert args[1] == "form1"  # prompt_node_id
        assert args[2] == "Data Collection"  # name
        assert args[_FORM_DEFINITION_ARG] == {}  # form_definition
        assert args[_RESPONDER_USER_IDS_ARG] == []  # responder_user_ids
        assert args[_RESPONDER_GROUP_IDS_ARG] == []  # responder_group_ids
        assert args[_LOOP_PATH_ARG] == []  # loop_iteration_path
        assert args[_TEMPORAL_ID_ARG] == "form1"  # temporal_activity_id

    @pytest.mark.asyncio
    async def test_form_prompt_args_inside_loop(self) -> None:
        """Loop-body form_prompts keep the canvas node id; path and Temporal id carry the index."""
        wf = _make_workflow()
        wf.loop_body_map["form1"] = "loop"
        wf.node_control_data["loop"] = {"current_index": 1, "next_port": "iterate"}
        graph = _build_form_prompt_graph()
        node = ActivityNode("form1", "form_prompt", {}, name="Data Collection")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, node.parameters)

        assert args[1] == "form1"
        assert args[_LOOP_PATH_ARG] == [1]
        assert args[_TEMPORAL_ID_ARG] == "form1_iter_1"

    @pytest.mark.asyncio
    async def test_form_prompt_args_with_responder_config(self) -> None:
        """Responder users and groups are correctly resolved to UUIDs."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph()
        config = {
            "responder_users": ["alice", "bob"],
            "responder_groups": ["data-team"],
        }
        node = ActivityNode("form1", "form_prompt", config, name="Data Entry")

        alice_id = str(uuid4())
        bob_id = str(uuid4())
        data_team_id = str(uuid4())

        mock_execute = AsyncMock(return_value={"user_ids": [alice_id, bob_id], "group_ids": [data_team_id]})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, config)

        assert len(args) == _NEW_FORM_PROMPT_ARG_COUNT
        assert args[_RESPONDER_USER_IDS_ARG] == [alice_id, bob_id]
        assert args[_RESPONDER_GROUP_IDS_ARG] == [data_team_id]

        # Verify the resolution activity was called
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["args"] == [["alice", "bob"], ["data-team"]]

    @pytest.mark.asyncio
    async def test_timeout_at_computed_from_response_window(self) -> None:
        """timeout_at is ISO string set to now + response_window when configured."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph()
        node = ActivityNode("form1", "form_prompt", {"response_window": 1800}, name="Form")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, {"response_window": 1800})

        timeout_at = args[_TIMEOUT_AT_ARG]
        assert timeout_at is not None
        parsed = datetime.fromisoformat(timeout_at)
        mock_now = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
        assert parsed == mock_now + timedelta(seconds=1800)

    @pytest.mark.asyncio
    async def test_name_fallback_to_node_id(self) -> None:
        """Name falls back to 'Form prompt for {id}' when config has no name."""
        wf = _make_workflow()
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("my_form", {"id": "my_form", "type": "form_prompt", "parameters": {}})
        backend.add_node("next", {"id": "next", "type": "script", "name": "Next Step", "parameters": {}})
        backend.add_edge("trigger", "my_form", None)
        backend.add_edge("my_form", "next", {"from_port": "submitted"})
        graph = WorkflowGraph(backend)
        graph.metadata = {"name": "Test"}
        node = ActivityNode("my_form", "form_prompt", {})

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, node.parameters)

        assert args[2] == "Form prompt for my_form"

    @pytest.mark.asyncio
    async def test_form_definition_passed_through(self) -> None:
        """form_definition from resolved_parameters is included in args."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph()
        form_def = {"fields": [{"name": "email", "type": "string"}]}
        config = {"form_definition": form_def}
        node = ActivityNode("form1", "form_prompt", config, name="Form")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, config)

        assert args[_FORM_DEFINITION_ARG] == form_def

    @pytest.mark.asyncio
    async def test_message_scrubbed_and_truncated(self) -> None:
        """Message field is scrubbed of secrets and truncated."""
        wf = _make_workflow()
        wf._secret_values = {"secret123"}
        graph = _build_form_prompt_graph()
        config = {"message": "Please enter secret123 carefully"}
        node = ActivityNode("form1", "form_prompt", config, name="Form")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, config)

        message = args[_MESSAGE_ARG]
        assert "secret123" not in message
        assert "[REDACTED]" in message

    @pytest.mark.asyncio
    async def test_presentation_fields_passed_through(self) -> None:
        """submit_label, success_message, timezone, css_override are all passed through."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph()
        config = {
            "submit_label": "Send",
            "success_message": "Thanks!",
            "timezone": "America/New_York",
            "css_override": ".form { color: blue; }",
        }
        node = ActivityNode("form1", "form_prompt", config, name="Form")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_form_prompt_args(node, graph, config)

        assert args[_SUBMIT_LABEL_ARG] == "Send"
        assert args[_SUCCESS_MESSAGE_ARG] == "Thanks!"
        assert args[_TIMEZONE_ARG] == "America/New_York"
        assert args[_CSS_OVERRIDE_ARG] == ".form { color: blue; }"

    @pytest.mark.asyncio
    async def test_missing_submitted_successor_raises(self) -> None:
        """A form prompt with nothing wired to 'submitted' has no destination for a response."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph(with_successor=False)
        node = ActivityNode("form1", "form_prompt", {}, name="Data Collection")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with (
            patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute),
            pytest.raises(SafeValueError, match="no submitted successor"),
        ):
            await wf._prepare_form_prompt_args(node, graph, node.parameters)


class TestExecuteFormPromptNode:
    """Tests for _execute_form_prompt_node method."""

    @pytest.mark.asyncio
    async def test_successful_submission_returns_submitted_outcome(self) -> None:
        """Successful form submission returns outcome=submitted and routes to submitted port."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph()
        node = ActivityNode("form1", "form_prompt", {}, name="Form")

        mock_prep_args = AsyncMock(return_value=[])
        mock_execute = AsyncMock(
            return_value={
                "output": {
                    "outcome": "submitted",
                    "response_data": {"email": "user@example.com"},
                    "responded_by": str(uuid4()),
                    "responded_at": "2026-04-10T12:05:00Z",
                    "prompt_id": str(uuid4()),
                }
            }
        )

        with (
            patch.object(wf, "_prepare_form_prompt_args", mock_prep_args),
            patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute),
        ):
            result = await wf._execute_form_prompt_node(node, graph, {})

        assert result["output"]["outcome"] == "submitted"
        assert result["output"]["response_data"] == {"email": "user@example.com"}
        assert result["control"]["next_port"] == "submitted"

    @pytest.mark.asyncio
    async def test_timeout_propagates_to_orchestrator(self) -> None:
        """Timeout exceptions propagate to orchestrator for COF handling."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph()
        node = ActivityNode("form1", "form_prompt", {}, name="Form")

        mock_prep_args = AsyncMock(return_value=[])

        # Create a real ActivityError with a mocked cause property
        timeout_error = TemporalTimeoutError("Activity timed out", type=None, last_heartbeat_details=[])
        activity_error = ActivityError(
            "Timeout",
            scheduled_event_id=1,
            started_event_id=2,
            identity="test",
            activity_type="form_prompt",
            activity_id="form1",
            retry_state=None,
        )
        # Mock the cause property to return our timeout error
        type(activity_error).cause = PropertyMock(return_value=timeout_error)  # type: ignore[method-assign]

        mock_execute = AsyncMock(side_effect=activity_error)

        with (
            patch.object(wf, "_prepare_form_prompt_args", mock_prep_args),
            patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute),
            pytest.raises(ActivityError),
        ):
            await wf._execute_form_prompt_node(node, graph, {})

    @pytest.mark.asyncio
    async def test_invalid_outcome_raises(self) -> None:
        """Invalid outcome raises ApplicationError."""
        wf = _make_workflow()
        graph = _build_form_prompt_graph()
        node = ActivityNode("form1", "form_prompt", {}, name="Form")

        mock_prep_args = AsyncMock(return_value=[])
        mock_execute = AsyncMock(
            return_value={
                "output": {
                    "outcome": "invalid_status",
                    "response_data": None,
                }
            }
        )

        with (
            patch.object(wf, "_prepare_form_prompt_args", mock_prep_args),
            patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute),
            pytest.raises(ApplicationError, match="Invalid form prompt outcome"),
        ):
            await wf._execute_form_prompt_node(node, graph, {})


class TestFormPromptCleanupMethods:
    """Tests for cleanup and lifecycle methods."""

    @pytest.mark.asyncio
    async def test_expire_form_prompts_calls_activity(self) -> None:
        """_expire_form_prompts calls the expire activity with correct args."""
        wf = _make_workflow()
        mock_execute = AsyncMock()

        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            await wf._expire_form_prompts("form1", activity_id="expire_form1")

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["args"] == ["exec-123", "form1"]

    @pytest.mark.asyncio
    async def test_cancel_form_prompts_calls_activity(self) -> None:
        """_cancel_form_prompts calls the cancel activity."""
        wf = _make_workflow()
        mock_execute = AsyncMock()

        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_activity", mock_execute):
            await wf._cancel_form_prompts()

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["args"] == ["exec-123"]

    @pytest.mark.asyncio
    async def test_fail_detached_form_prompt_activity_calls_local_activity(self) -> None:
        """_fail_detached_form_prompt_activity calls the fail activity with correct args."""
        wf = _make_workflow()
        mock_execute = AsyncMock()

        with patch("syntara.workflows.workflow_engine.form_prompt_mixin.workflow.execute_local_activity", mock_execute):
            await wf._fail_detached_form_prompt_activity("form1")

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args.kwargs["args"]
        assert call_args == ["test-wf-id", "test-run-id", "form1"]

    @pytest.mark.asyncio
    async def test_expire_remaining_form_prompts_expires_and_fails_detached(self) -> None:
        """_expire_remaining_form_prompts expires all and fails detached activities."""
        wf = _make_workflow()
        wf._detached_nodes = {"form1", "form2"}

        backend = InMemoryGraphBackend()
        backend.add_node("form1", {"id": "form1", "type": "form_prompt", "parameters": {}})
        backend.add_node("form2", {"id": "form2", "type": "form_prompt", "parameters": {}})
        graph = WorkflowGraph(backend)

        mock_expire = AsyncMock()
        mock_fail = AsyncMock()

        with (
            patch.object(wf, "_expire_form_prompts", mock_expire),
            patch.object(wf, "_fail_detached_form_prompt_activity", mock_fail),
        ):
            await wf._expire_remaining_form_prompts(graph)

        # Should expire all prompts for execution
        mock_expire.assert_called_once()
        call_kwargs = mock_expire.call_args.kwargs
        assert call_kwargs["node_id"] is None

        # Should fail both detached activities
        assert mock_fail.call_count == 2
