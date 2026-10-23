"""Real V2 graph, approval provider, PostgreSQL inbox, and Temporal completion."""

import asyncio
import shutil
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.approvals.activities import ApprovalActivities
from syntara.approvals.models.api_models import ApprovalDecisionRequest, ApprovalDecisionStatus
from syntara.approvals.models.approval_request import ApprovalRequest
from syntara.approvals.registration import register_approval_activities
from syntara.approvals.services.approval_service import ApprovalService
from syntara.core.lib.encryption import SecretEncryptor
from syntara.core.models.user import User
from syntara.settings.cache import settings_cache
from syntara.workflow_runtime.engines.temporal.dynamic_workflow import OrchestratorWorkflow
from syntara.workflow_runtime.engines.temporal.registered_activities import CompletionDelivery, RegisteredActivities
from syntara.workflow_runtime.models import ActivityCompletion
from syntara.workflow_runtime.registry import ActivityRegistry
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.activities.condition import condition
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from tests.fixtures.settings import FakeSettingsCache


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", [ApprovalDecisionStatus.APPROVED, ApprovalDecisionStatus.REJECTED])
async def test_registered_approval_completes_v2_graph(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_execution: Execution,
    test_user: User,
    decision: ApprovalDecisionStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real handler defers; an authorized decision resumes the correct graph branch."""
    temporal_cli = shutil.which("temporal")
    if temporal_cli is None:
        pytest.skip("Temporal CLI is required for real async-completion RPCs")
    monkeypatch.setattr(settings_cache, "_runtime_settings", FakeSettingsCache())
    registry = ActivityRegistry()
    register_approval_activities(registry, ApprovalActivities(test_db_session_factory))
    encryptor = SecretEncryptor(bytes(range(32)))
    adapter = RegisteredActivities(registry, test_db_session_factory, encryptor)
    definition: dict[str, Any] = {
        "schema_version": "2.0.0",
        "name": "Registered approval",
        "triggers": [{"id": "start", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {"id": "review", "type": "approval", "parameters": {"prompt": "Review this run", "decision_window": 60}},
            {"id": "approved", "type": "condition", "parameters": {"condition": "True"}},
            {"id": "rejected", "type": "condition", "parameters": {"condition": "True"}},
        ],
        "edges": [
            {"from": "start", "to": "review"},
            {"from": "review", "to": "approved", "from_port": "approved"},
            {"from": "review", "to": "rejected", "from_port": "rejected"},
        ],
    }
    metadata = {
        "workflow_context": {
            "workflow": {
                "id": str(test_execution.workflow_id),
                "project_id": str(test_execution.project_id),
                "version": 1,
            }
        }
    }
    async with await WorkflowEnvironment.start_local(dev_server_existing_path=temporal_cli) as env:
        queue = f"approval-prototype-{uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[OrchestratorWorkflow],
            activities=[adapter.execute, manual_trigger, condition, fetch_workflow_runtime_settings],
        ):
            handle = await env.client.start_workflow(
                OrchestratorWorkflow.run,
                args=[definition, str(test_execution.id), "start", {}, True, None, None, None, metadata],
                id=f"prototype-{uuid4()}",
                task_queue=queue,
            )
            async with asyncio.timeout(30):
                while True:
                    async with test_db_session_factory() as session:
                        approval = (
                            await session.exec(
                                select(ApprovalRequest).where(ApprovalRequest.execution_id == test_execution.id)
                            )
                        ).first()
                    if approval is not None:
                        break
                    await asyncio.sleep(0.1)
            assert approval.completion_ref is not None
            service = ApprovalService(test_db_session, test_user, evaluator=MagicMock())
            with (
                patch.object(service, "_has_permission", AsyncMock(return_value=True)),
                patch(
                    "syntara.approvals.services.approval_service.WorkflowApiClient",
                    side_effect=AssertionError("HTTP callback used"),
                ),
            ):
                response = await service.decide(approval.id, ApprovalDecisionRequest(status=decision))
            assert response.signal_delivery_error is None
            # Construct delivery after the decision, as on a worker restart.
            delivery = CompletionDelivery(env.client, test_db_session_factory, encryptor)
            async with asyncio.timeout(30):
                while True:
                    await delivery.deliver_pending()
                    async with test_db_session_factory() as session:
                        completion = await session.get(ActivityCompletion, approval.completion_ref)
                        if completion is not None and completion.state == "delivered":
                            break
                    await asyncio.sleep(0.1)
                result = await handle.result()
            assert result["status"] == "completed"
            assert result["activity_outputs"]["review"]["decision"] == decision.value
            assert decision.value in result["completed_activities"]
            other_branch = "rejected" if decision == ApprovalDecisionStatus.APPROVED else "approved"
            assert other_branch not in result["completed_activities"]
