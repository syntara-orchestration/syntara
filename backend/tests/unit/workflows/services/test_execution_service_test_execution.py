"""Unit tests for ExecutionService.create_test_execution method.

Tests verify the test execution creation logic including validation,
Temporal integration, and database operations.
"""

from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.metrics.interface_tag import interface_context_var
from syntara.workflows.exceptions import WorkflowNotFoundError
from syntara.workflows.models.execution import (
    ExecutionMode,
    ExecutionStatus,
    PreResolvedNodeOutput,
    TestExecutionCreate,
)
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


def _make_mock_workflow(
    *,
    workflow_id: UUID | None = None,
    version_id: UUID | None = None,
    is_enabled: bool = True,
    node_ids: list[str] | None = None,
) -> tuple[Mock, Mock]:
    """Build mock Workflow + WorkflowVersion pair."""
    wf = Mock(spec=Workflow)
    wf.id = workflow_id or uuid4()
    wf.name = "test-workflow"
    wf.is_enabled = is_enabled
    wf.project_id = uuid4()

    wv = Mock(spec=WorkflowVersion)
    wv.id = version_id or uuid4()
    wv.version = 1
    wv.schema_version = "2.0.0"
    wv.workflow_definition = {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger_1", "type": "manual"}],
        "nodes": [{"id": nid, "type": "script"} for nid in (node_ids or ["target_node"])],
        "edges": [],
    }
    return wf, wv


def _make_service(
    *,
    query_result: tuple[Mock, Mock] | None,
    temporal_service: Mock | None = None,
    user_id: UUID | None = None,
) -> tuple[ExecutionService, Mock]:
    """Build ExecutionService with mocked session returning query_result."""
    session = Mock(spec=AsyncSession)
    mock_result = Mock()
    mock_result.first = Mock(return_value=query_result)
    session.exec = AsyncMock(return_value=mock_result)
    session.add = Mock()
    session.commit = AsyncMock()

    user = Mock(spec=User)
    user.id = user_id or uuid4()

    svc = ExecutionService(session=session, user=user, temporal_service=temporal_service)
    return svc, session


class TestCreateTestExecution:
    """Test create_test_execution method."""

    @pytest.mark.asyncio
    async def test_success_returns_execution_with_test_mode(self) -> None:
        """Successful creation returns ExecutionRead with mode=TEST and status=PENDING."""
        wf, wv = _make_mock_workflow(node_ids=["node_1", "node_2", "target_node"])
        exec_id = uuid4()
        temporal = Mock()
        temporal_result = Mock()
        temporal_result.execution_id = str(exec_id)
        temporal_result.temporal_workflow_id = "test-exec-abc"
        temporal_result.temporal_run_id = "run-xyz"
        temporal.start_workflow = AsyncMock(return_value=temporal_result)

        service, _ = _make_service(query_result=(wf, wv), temporal_service=temporal)

        result = await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={"node_1": PreResolvedNodeOutput(output={"v": 1})},
            trigger_inputs={"key": "val"},
            trigger_node_id="trigger_1",
        )

        assert result.id == exec_id
        assert result.status == ExecutionStatus.PENDING
        assert result.mode == ExecutionMode.TEST
        assert result.temporal_workflow_id == "test-exec-abc"

    @pytest.mark.asyncio
    async def test_success_stores_converted_pre_resolved_in_metadata(self) -> None:
        """Pre-resolved nodes are model_dump'd before storing in execution_metadata."""
        wf, wv = _make_mock_workflow(node_ids=["node_1", "target_node"])
        exec_id = uuid4()
        temporal = Mock()
        temporal_result = Mock()
        temporal_result.execution_id = str(exec_id)
        temporal_result.temporal_workflow_id = "test-exec-abc"
        temporal_result.temporal_run_id = "run-xyz"
        temporal.start_workflow = AsyncMock(return_value=temporal_result)

        service, session = _make_service(query_result=(wf, wv), temporal_service=temporal)

        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={"node_1": PreResolvedNodeOutput(output={"r": "mocked"})},
            trigger_inputs={},
            trigger_node_id="trigger_1",
        )

        execution = session.add.call_args[0][0]
        assert execution.execution_metadata["target_node_id"] == "target_node"
        assert execution.execution_metadata["pre_resolved_nodes"]["node_1"] == {
            "output": {"r": "mocked"},
            "control": None,
        }

    @pytest.mark.asyncio
    async def test_success_passes_dicts_to_temporal(self) -> None:
        """Temporal receives plain dicts, not PreResolvedNodeOutput objects."""
        wf, wv = _make_mock_workflow(node_ids=["node_1", "target_node"])
        exec_id = uuid4()
        temporal = Mock()
        temporal_result = Mock()
        temporal_result.execution_id = str(exec_id)
        temporal_result.temporal_workflow_id = "t"
        temporal_result.temporal_run_id = "r"
        temporal.start_workflow = AsyncMock(return_value=temporal_result)

        service, _ = _make_service(query_result=(wf, wv), temporal_service=temporal)

        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={"node_1": PreResolvedNodeOutput(output={"v": 1})},
            trigger_inputs={},
            trigger_node_id="trigger_1",
        )

        call_kwargs = temporal.start_workflow.call_args.kwargs
        assert call_kwargs["pre_resolved_outputs"] == {"node_1": {"output": {"v": 1}, "control": None}}
        assert call_kwargs["stop_after_nodes"] == ["target_node"]

        # Verify workflow_metadata includes project_id (prevents approval activity regression)
        wf_meta = call_kwargs["workflow_metadata"]
        assert wf_meta is not None
        assert wf_meta["workflow_context"]["workflow"]["project_id"] == str(wf.project_id)
        assert wf_meta["workflow_context"]["execution"]["mode"] == "test"

    @pytest.mark.asyncio
    async def test_success_without_temporal_uses_stub_id(self) -> None:
        """When Temporal is unavailable, a stub workflow ID is generated."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        service, _ = _make_service(query_result=(wf, wv), temporal_service=None)

        result = await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={},
            trigger_inputs={},
            trigger_node_id="trigger_1",
        )

        assert result.temporal_workflow_id.startswith("test-exec-")
        UUID(result.temporal_workflow_id.replace("test-exec-", ""))
        assert result.mode == ExecutionMode.TEST

    @pytest.mark.asyncio
    async def test_workflow_not_found_raises(self) -> None:
        """Non-existent workflow raises WorkflowNotFoundError."""
        service, _ = _make_service(query_result=None)
        wf_id = uuid4()

        with pytest.raises(WorkflowNotFoundError) as exc_info:
            await service.create_test_execution(
                workflow_id=wf_id,
                target_node_id="target_node",
                pre_resolved_nodes={},
                trigger_inputs={},
                trigger_node_id="trigger_1",
            )
        assert str(wf_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disabled_workflow_allowed(self) -> None:
        """Test execution is allowed on disabled workflows (unlike normal runs)."""
        wf, wv = _make_mock_workflow(is_enabled=False, node_ids=["target_node"])
        service, _ = _make_service(query_result=(wf, wv), temporal_service=None)

        result = await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={},
            trigger_inputs={},
            trigger_node_id="trigger_1",
        )

        assert result.mode == ExecutionMode.TEST

    @pytest.mark.asyncio
    async def test_invalid_target_node_raises(self) -> None:
        """Invalid target_node_id raises SafeValueError with available nodes."""
        wf, wv = _make_mock_workflow(node_ids=["node_1", "node_2"])
        service, _ = _make_service(query_result=(wf, wv))

        with pytest.raises(SafeValueError) as exc_info:
            await service.create_test_execution(
                workflow_id=wf.id,
                target_node_id="nonexistent",
                pre_resolved_nodes={},
                trigger_inputs={},
                trigger_node_id="trigger_1",
            )

        msg = str(exc_info.value)
        assert "nonexistent" in msg
        assert "node_1" in msg

    @pytest.mark.asyncio
    async def test_invalid_pre_resolved_keys_raises(self) -> None:
        """Pre-resolved nodes referencing unknown IDs raise SafeValueError."""
        wf, wv = _make_mock_workflow(node_ids=["node_1", "target_node"])
        service, _ = _make_service(query_result=(wf, wv))

        with pytest.raises(SafeValueError) as exc_info:
            await service.create_test_execution(
                workflow_id=wf.id,
                target_node_id="target_node",
                pre_resolved_nodes={
                    "node_1": PreResolvedNodeOutput(output={}),
                    "unknown": PreResolvedNodeOutput(output={}),
                },
                trigger_inputs={},
                trigger_node_id="trigger_1",
            )

        assert "unknown" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_temporal_failure_propagates(self) -> None:
        """Temporal start_workflow failure propagates exception."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        temporal = Mock()
        temporal.start_workflow = AsyncMock(side_effect=RuntimeError("Temporal unavailable"))
        service, _ = _make_service(query_result=(wf, wv), temporal_service=temporal)

        with pytest.raises(RuntimeError, match="Temporal unavailable"):
            await service.create_test_execution(
                workflow_id=wf.id,
                target_node_id="target_node",
                pre_resolved_nodes={},
                trigger_inputs={},
                trigger_node_id="trigger_1",
            )

    @pytest.mark.asyncio
    async def test_target_in_pre_resolved_raises(self) -> None:
        """target_node_id in pre_resolved_nodes is rejected."""
        wf, wv = _make_mock_workflow(node_ids=["node_1", "target_node"])
        service, _ = _make_service(query_result=(wf, wv))
        with pytest.raises(SafeValueError, match="must not appear"):
            await service.create_test_execution(
                workflow_id=wf.id,
                target_node_id="target_node",
                pre_resolved_nodes={"target_node": PreResolvedNodeOutput(output={})},
                trigger_inputs={},
                trigger_node_id="trigger_1",
            )

    @pytest.mark.asyncio
    async def test_create_test_execution_execute_target_false_adds_target_to_pre_resolved(self) -> None:
        """When execute_target is False, target_node_id is added to pre_resolved_nodes."""
        wf, wv = _make_mock_workflow(node_ids=["node_1", "target_node"])
        exec_id = uuid4()
        temporal = Mock()
        temporal_result = Mock()
        temporal_result.execution_id = str(exec_id)
        temporal_result.temporal_workflow_id = "test-exec-abc"
        temporal_result.temporal_run_id = "run-xyz"
        temporal.start_workflow = AsyncMock(return_value=temporal_result)

        service, session = _make_service(query_result=(wf, wv), temporal_service=temporal)

        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={"node_1": PreResolvedNodeOutput(output={"v": 1})},
            trigger_inputs={},
            execute_target=False,
            trigger_node_id="trigger_1",
        )

        # Verify Temporal was called with target_node in pre_resolved_outputs
        call_kwargs = temporal.start_workflow.call_args.kwargs
        assert "target_node" in call_kwargs["pre_resolved_outputs"]
        assert call_kwargs["pre_resolved_outputs"]["target_node"] == {"output": {}, "control": None}

        # Verify execution_metadata includes execute_target
        execution = session.add.call_args[0][0]
        assert execution.execution_metadata["execute_target"] is False

    @pytest.mark.asyncio
    async def test_create_test_execution_execute_target_false_does_not_double_add(self) -> None:
        """When execute_target is False and target already in pre_resolved, do not overwrite."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        exec_id = uuid4()
        temporal = Mock()
        temporal_result = Mock()
        temporal_result.execution_id = str(exec_id)
        temporal_result.temporal_workflow_id = "test-exec-abc"
        temporal_result.temporal_run_id = "run-xyz"
        temporal.start_workflow = AsyncMock(return_value=temporal_result)

        service, session = _make_service(query_result=(wf, wv), temporal_service=temporal)

        original_output = {"custom": "value"}
        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={"target_node": PreResolvedNodeOutput(output=original_output)},
            trigger_inputs={},
            execute_target=False,
            trigger_node_id="trigger_1",
        )

        # Verify the existing entry is preserved (not overwritten)
        call_kwargs = temporal.start_workflow.call_args.kwargs
        assert call_kwargs["pre_resolved_outputs"]["target_node"] == {"output": original_output, "control": None}

        # Verify execution_metadata includes execute_target
        execution = session.add.call_args[0][0]
        assert execution.execution_metadata["execute_target"] is False

    @pytest.mark.asyncio
    async def test_trigger_type_extracted_from_workflow_triggers(self) -> None:
        """Test that trigger_type is extracted from the first matching trigger in workflow definition."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        # Override workflow_definition to include a valid trigger type
        wv.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_1", "type": NodeType.WEBHOOK_TRIGGER}],
            "nodes": [{"id": "target_node", "type": "script"}],
            "edges": [],
        }
        service, session = _make_service(query_result=(wf, wv), temporal_service=None)

        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={},
            trigger_inputs={},
            trigger_node_id="trigger_1",
        )

        execution = session.add.call_args[0][0]
        assert execution.trigger_type == NodeType.WEBHOOK_TRIGGER

    @pytest.mark.asyncio
    async def test_trigger_type_none_when_no_triggers(self) -> None:
        """Test that trigger_type is None when workflow has no triggers."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        # Override workflow_definition with no triggers
        wv.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [],
            "nodes": [{"id": "target_node", "type": "script"}],
            "edges": [],
        }
        service, session = _make_service(query_result=(wf, wv), temporal_service=None)

        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={},
            trigger_inputs={},
            trigger_node_id="trigger_manual",
        )

        execution = session.add.call_args[0][0]
        assert execution.trigger_type is None

    @pytest.mark.asyncio
    async def test_trigger_type_none_when_no_matching_trigger_type(self) -> None:
        """Test that trigger_type is None when triggers exist but none end with '_trigger'."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        # Default _make_mock_workflow uses "manual" (not "manual_trigger"),
        # which does not match the _trigger suffix filter
        service, session = _make_service(query_result=(wf, wv), temporal_service=None)

        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={},
            trigger_inputs={},
            trigger_node_id="trigger_manual",
        )

        execution = session.add.call_args[0][0]
        assert execution.trigger_type is None

    @pytest.mark.asyncio
    async def test_interface_set_from_context_var(self) -> None:
        """Test that interface is set from interface_context_var."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        service, session = _make_service(query_result=(wf, wv), temporal_service=None)

        token = interface_context_var.set("ui")
        try:
            await service.create_test_execution(
                workflow_id=wf.id,
                target_node_id="target_node",
                pre_resolved_nodes={},
                trigger_inputs={},
                trigger_node_id="trigger_manual",
            )

            execution = session.add.call_args[0][0]
            assert execution.interface == "ui"
        finally:
            interface_context_var.reset(token)

    @pytest.mark.asyncio
    async def test_interface_defaults_to_api(self) -> None:
        """Test that interface defaults to 'api' when context var is not explicitly set."""
        wf, wv = _make_mock_workflow(node_ids=["target_node"])
        service, session = _make_service(query_result=(wf, wv), temporal_service=None)

        await service.create_test_execution(
            workflow_id=wf.id,
            target_node_id="target_node",
            pre_resolved_nodes={},
            trigger_inputs={},
            trigger_node_id="trigger_manual",
        )

        execution = session.add.call_args[0][0]
        assert execution.interface == "api"


# Validator tests — test the Pydantic model directly
def test_pre_resolved_nodes_max_100_passes() -> None:
    """Validator accepts exactly 100 pre-resolved nodes."""
    nodes = {f"node_{i}": PreResolvedNodeOutput(output={}) for i in range(100)}
    req = TestExecutionCreate(target_node_id="target", pre_resolved_nodes=nodes, trigger_node_id="trigger_1")
    assert len(req.pre_resolved_nodes) == 100


def test_pre_resolved_nodes_over_100_raises() -> None:
    """Validator rejects more than 100 pre-resolved nodes."""
    nodes = {f"node_{i}": PreResolvedNodeOutput(output={}) for i in range(101)}
    with pytest.raises(ValidationError):
        TestExecutionCreate(target_node_id="target", pre_resolved_nodes=nodes, trigger_node_id="trigger_1")


def test_empty_target_node_id_raises() -> None:
    """Validator rejects empty target_node_id."""
    with pytest.raises(ValidationError):
        TestExecutionCreate(target_node_id="", pre_resolved_nodes={})


def test_whitespace_target_node_id_raises() -> None:
    """Validator rejects whitespace-only target_node_id."""
    with pytest.raises(ValidationError):
        TestExecutionCreate(target_node_id="   ", pre_resolved_nodes={})


def test_target_node_id_stripped() -> None:
    """Validator strips whitespace from target_node_id."""
    req = TestExecutionCreate(target_node_id="  node_a  ", pre_resolved_nodes={}, trigger_node_id="trigger_1")
    assert req.target_node_id == "node_a"


def test_target_in_pre_resolved_raises_at_model_level() -> None:
    """Model validator rejects target_node_id appearing in pre_resolved_nodes."""
    with pytest.raises(ValidationError, match="must not appear"):
        TestExecutionCreate(
            target_node_id="node_a",
            pre_resolved_nodes={"node_a": PreResolvedNodeOutput(output={})},
            trigger_node_id="trigger_1",
        )


def test_target_in_pre_resolved_allowed_when_execute_target_false() -> None:
    """Validator allows target_node_id in pre_resolved_nodes when execute_target is False."""
    req = TestExecutionCreate(
        target_node_id="target",
        pre_resolved_nodes={"target": PreResolvedNodeOutput(output={"v": 1})},
        execute_target=False,
        trigger_node_id="trigger_1",
    )
    assert req.target_node_id == "target"
    assert "target" in req.pre_resolved_nodes
    assert req.execute_target is False


def test_target_in_pre_resolved_rejected_when_execute_target_true() -> None:
    """Validator rejects target_node_id in pre_resolved_nodes when execute_target is True."""
    with pytest.raises(ValidationError, match="must not appear"):
        TestExecutionCreate(
            target_node_id="target",
            pre_resolved_nodes={"target": PreResolvedNodeOutput(output={})},
            execute_target=True,
            trigger_node_id="trigger_1",
        )


def test_execute_target_defaults_to_true() -> None:
    """Validator sets execute_target to True by default."""
    req = TestExecutionCreate(
        target_node_id="target",
        pre_resolved_nodes={},
        trigger_node_id="trigger_1",
    )
    assert req.execute_target is True
