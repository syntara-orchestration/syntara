"""The launch carries the run principal and signed node execute decisions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.workflow_engine.scheduled_launcher import ScheduledExecutionLauncher
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow


def _interactive_service() -> tuple[ExecutionService, UUID, UUID, Mock]:
    user = Mock(spec=User)
    user.id = uuid4()
    workflow = Mock(spec=Workflow)
    workflow.id = uuid4()
    workflow.name = "node-permission-test"
    workflow.created_by = user.id
    workflow.project_id = uuid4()
    workflow.is_builtin = False
    workflow.published_version_id = None
    version = Mock(spec=WorkflowVersion)
    version.id = uuid4()
    version.version = 1
    version.schema_version = "2.0.0"
    version.workflow_definition = {
        "schema_version": "2.0.0",
        "triggers": [{"id": "start", "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "script", "type": "script", "parameters": {}}],
        "edges": [{"from": "start", "to": "script"}],
    }
    query = Mock()
    query.first.return_value = (workflow, version)
    session = Mock(spec=AsyncSession)
    session.exec = AsyncMock(side_effect=lambda statement: [] if "principals" in str(statement).lower() else query)
    session.scalar = AsyncMock(return_value=0)
    session.commit = AsyncMock()
    temporal = Mock()
    temporal.start_workflow = AsyncMock(
        return_value=SimpleNamespace(
            execution_id=str(uuid4()), temporal_workflow_id="temporal-1", temporal_run_id="run-1"
        )
    )
    return ExecutionService(session=session, user=user, temporal_service=temporal), workflow.id, user.id, temporal


class TestInteractiveRunPrincipal:
    """Interactive runs use the person who started the run."""

    @pytest.mark.parametrize("test_run", [False, True], ids=["manual-run", "test-run"])
    async def test_invoker_is_the_node_permission_principal(self, test_run: bool) -> None:  # noqa: FBT001
        service, workflow_id, user_id, temporal = _interactive_service()

        if test_run:
            await service.create_test_execution(
                workflow_id=workflow_id,
                target_node_id="script",
                pre_resolved_nodes={},
                trigger_inputs={},
                trigger_node_id="start",
            )
        else:
            await service.create_execution(
                workflow_id=workflow_id,
                input_data={},
                trigger_node_id="start",
            )

        assert temporal.start_workflow.call_args.kwargs["run_principal_id"] == str(user_id)


class TestTriggeredRunPrincipal:
    """Automated runs use the published version's publisher."""

    async def test_schedule_uses_the_publisher(self) -> None:
        publisher_id = uuid4()
        author_id = uuid4()
        workflow = Mock(spec=Workflow)
        workflow.id = uuid4()
        workflow.name = "scheduled-test"
        workflow.project_id = uuid4()
        workflow.created_by = author_id
        version = Mock(spec=WorkflowVersion)
        version.id = uuid4()
        version.version = 1
        version.published_by = publisher_id
        version.workflow_definition = {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []}
        session = AsyncMock(spec=AsyncSession)
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        launcher = ScheduledExecutionLauncher(session_factory=factory, task_queue="test")

        with (
            patch.object(launcher, "_load_published_workflow", return_value=(workflow, version)),
            patch("syntara.workflows.workflow_engine.scheduled_launcher.get_settings") as settings,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.resolve_user_display_name",
                return_value="Author",
            ),
        ):
            settings.return_value.service_identity = "backend.test.svc"
            settings.return_value.max_concurrent_workflows = 0
            result = await launcher._create_execution(workflow.id, "start", datetime.now(UTC), datetime.now(UTC))

        assert result["run_principal_id"] == str(publisher_id)


class TestSignedDeniedNodes:
    """Denied decisions travel with the workflow and cannot be changed after signing."""

    async def test_temporal_starts_even_with_denied_nodes(self) -> None:
        denied = [{"node_id": "script", "labels": {"kind": "script"}, "denied_by": "deny-script"}]
        principal_id = str(uuid4())
        client = Mock()
        client.start_workflow = AsyncMock(return_value=SimpleNamespace(first_execution_run_id="run-1"))
        service = TemporalExecutionService(temporal_client=client, task_queue="test")

        await service.start_workflow(
            workflow_def={
                "schema_version": "2.0.0",
                "triggers": [{"id": "start", "type": "manual_trigger", "parameters": {}}],
                "nodes": [{"id": "script", "type": "script", "parameters": {}}],
                "edges": [{"from": "start", "to": "script"}],
            },
            workflow_name="denied-node",
            trigger_node_id="start",
            denied_nodes=denied,
            run_principal_id=principal_id,
        )

        args = client.start_workflow.call_args.kwargs["args"]
        assert denied in args
        assert principal_id in args

    def test_changing_denied_nodes_invalidates_the_workflow_signature(self) -> None:
        args = ["definition", "execution-id", [{"node_id": "script", "denied_by": "deny-script"}]]

        with patch("syntara.workflows.workflow_engine.workflow_auth._get_signing_key", return_value=b"t" * 32):
            token = sign_workflow("workflow-id", "orchestrator_workflow", args)
            changed_args = [*args[:-1], []]
            assert verify_workflow("workflow-id", "orchestrator_workflow", args, token)
            assert not verify_workflow("workflow-id", "orchestrator_workflow", changed_args, token)
