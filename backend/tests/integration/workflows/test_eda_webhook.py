"""Integration tests for EDA webhook endpoint.

These tests verify HTTP routing, path validation, DB-backed trigger lookup,
and service account Bearer token authentication for the EDA webhook endpoint.
Temporal and ExecutionService are mocked since they are not available in the
integration test environment.

Run with: pytest tests/integration/workflows/test_eda_webhook.py -v
"""

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.models.principal import PrincipalType
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.webhook_trigger import WebhookTrigger
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.services.workflow_service import WorkflowService
from syntara.workflows.webhook_router import get_webhook_caller, get_webhook_temporal_service

pytestmark = pytest.mark.integration


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def _mock_webhook_caller() -> tuple[User, UUID]:
    """Build a mock SA caller for webhook auth."""
    sa_id = uuid4()
    user = User(
        id=sa_id,
        username="test-sa",
        email="test-sa@internal",
        first_name="test-sa",
        is_enabled=True,
    )
    object.__setattr__(user, "__principal_type__", PrincipalType.SERVICE_ACCOUNT)
    return user, sa_id


@pytest.fixture(autouse=True)
def _patch_webhook_caller(session_app: FastAPI, _mock_webhook_caller: tuple[User, UUID]) -> Generator[None]:
    """Override get_webhook_caller to return the mock SA caller for all tests."""
    session_app.dependency_overrides[get_webhook_caller] = lambda: _mock_webhook_caller
    yield
    session_app.dependency_overrides.pop(get_webhook_caller, None)


@pytest.fixture(autouse=True)
def _skip_sa_authorization() -> Generator[None]:
    """Skip SA authorization check — the caller is already mocked via get_webhook_caller."""
    with patch(
        "syntara.workflows.services.webhook_trigger_service.WebhookTriggerService.verify_service_account_authorization",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def _no_temporal(session_app: FastAPI) -> Generator[None]:
    """Override Temporal dependency to return None (simulate unavailability)."""
    session_app.dependency_overrides[get_webhook_temporal_service] = lambda: None
    yield
    session_app.dependency_overrides.pop(get_webhook_temporal_service, None)


@pytest_asyncio.fixture
async def eda_workflow(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> Workflow:
    """Create a published workflow with an EDA trigger and bind the mock SA."""
    workflow_definition = {
        "schema_version": "2.0.0",
        "name": "Test EDA Workflow",
        "triggers": [
            {
                "id": "eda_trigger_1",
                "type": "eda_trigger",
                "parameters": {
                    "webhook_path": "github-deployments",
                },
            }
        ],
        "nodes": [
            {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}},
        ],
        "edges": [{"from": "eda_trigger_1", "to": "n1"}],
    }

    service = WorkflowService(test_db_session, test_user)
    workflow, _version, _ = await service.create_workflow(
        name="Test EDA Workflow",
        description="Test workflow for EDA triggers",
        labels={},
        workflow_definition=workflow_definition,
        project_id=test_project_id,
    )
    workflow, _version, _warning = await service.publish_workflow_version(workflow.id, version=1)

    return workflow


@pytest_asyncio.fixture
async def eda_workflow_with_schema(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> Workflow:
    """Create a published EDA workflow with input_schema and bind the mock SA."""
    input_schema = {
        "type": "object",
        "required": ["event_type"],
        "properties": {
            "event_type": {"type": "string"},
        },
        "additionalProperties": True,
    }

    workflow_definition = {
        "schema_version": "2.0.0",
        "name": "Test EDA Workflow With Schema",
        "triggers": [
            {
                "id": "eda_trigger_validated",
                "type": "eda_trigger",
                "parameters": {
                    "webhook_path": "validated-events",
                    "input_schema": input_schema,
                },
            }
        ],
        "nodes": [
            {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}},
        ],
        "edges": [{"from": "eda_trigger_validated", "to": "n1"}],
    }

    service = WorkflowService(test_db_session, test_user)
    workflow, _version, _ = await service.create_workflow(
        name="Test EDA Workflow With Schema",
        description="EDA workflow with input_schema for validation tests",
        labels={},
        workflow_definition=workflow_definition,
        project_id=test_project_id,
    )
    workflow, _version, _warning = await service.publish_workflow_version(workflow.id, version=1)

    return workflow


@pytest_asyncio.fixture
async def temporal_client(
    session_app: FastAPI,
    test_db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient]:
    """Client with Temporal dependency overridden to return a mock service."""
    mock_temporal = AsyncMock()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db_session

    session_app.dependency_overrides[get_db] = override_get_db
    session_app.dependency_overrides[get_webhook_temporal_service] = lambda: mock_temporal

    async with AsyncClient(
        transport=ASGITransport(app=session_app),
        base_url="http://test",
    ) as client:
        yield client

    session_app.dependency_overrides.pop(get_webhook_temporal_service, None)


# ============================================================================
# Tests
# ============================================================================


class TestEDAWebhookAuth:
    """Test that the endpoint requires service account authentication."""

    async def test_webhook_requires_auth(self, session_app: FastAPI, test_db_session: AsyncSession) -> None:
        """Webhook endpoint returns 401 without authentication."""
        # Remove the auth override so the real dependency runs
        session_app.dependency_overrides.pop(get_webhook_caller, None)

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        session_app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=session_app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/webhooks/eda/test-path",
                json={"test": "data"},
            )

        assert response.status_code == 401


class TestEDAWebhookValidation:
    """Test request payload validation."""

    async def test_webhook_path_rejects_invalid_characters(self, base_client: AsyncClient) -> None:
        """Webhook path with uppercase letters is rejected by validation."""
        response = await base_client.post(
            "/api/v1/webhooks/eda/GitHub-Deployments",
            json={"test": "data"},
        )

        assert response.status_code == 422

    async def test_webhook_handles_malformed_json(self, base_client: AsyncClient) -> None:
        """Returns 422 for malformed JSON."""
        response = await base_client.post(
            "/api/v1/webhooks/eda/test-path",
            content='{"test": invalid json',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    async def test_webhook_rejects_payload_failing_input_schema(
        self,
        temporal_client: AsyncClient,
        eda_workflow_with_schema: Workflow,
    ) -> None:
        """Returns 422 when payload does not conform to the trigger's input_schema."""
        response = await temporal_client.post(
            "/api/v1/webhooks/eda/validated-events",
            json={"other_field": "value"},
        )

        assert response.status_code == 422
        body = response.json()
        assert "validation" in body.get("detail", "").lower()

    async def test_webhook_accepts_payload_matching_input_schema(
        self,
        temporal_client: AsyncClient,
        eda_workflow_with_schema: Workflow,
    ) -> None:
        """Returns 202 when payload conforms to the trigger's input_schema."""
        with patch("syntara.workflows.webhook_router.ExecutionService") as mock_exec_cls:
            mock_exec = AsyncMock()
            mock_exec_cls.return_value = mock_exec

            mock_execution = Mock(spec=Execution)
            mock_execution.id = uuid4()
            mock_exec.create_execution = AsyncMock(return_value=mock_execution)

            response = await temporal_client.post(
                "/api/v1/webhooks/eda/validated-events",
                json={"event_type": "deploy", "extra": "data"},
            )

            assert response.status_code == 202
            data = response.json()
            assert data["execution_id"] == str(mock_execution.id)


class TestEDAWebhookWorkflowMatching:
    """Test workflow matching by webhook path via lookup table."""

    async def test_webhook_returns_404_when_no_matching_trigger(
        self, base_client: AsyncClient, test_db_session: AsyncSession
    ) -> None:
        """Returns 404 when webhook_path has no matching lookup table row."""
        response = await base_client.post(
            "/api/v1/webhooks/eda/nonexistent-path",
            json={"test": "data"},
        )

        assert response.status_code == 404

    async def test_webhook_triggers_matching_workflow(
        self,
        temporal_client: AsyncClient,
        eda_workflow: Workflow,
    ) -> None:
        """Triggers workflow that matches webhook_path in lookup table."""
        with patch("syntara.workflows.webhook_router.ExecutionService") as mock_exec_service_class:
            mock_exec_service = AsyncMock()
            mock_exec_service_class.return_value = mock_exec_service

            mock_execution = Mock(spec=Execution)
            mock_execution.id = uuid4()
            mock_exec_service.create_execution = AsyncMock(return_value=mock_execution)

            response = await temporal_client.post(
                "/api/v1/webhooks/eda/github-deployments",
                json={
                    "repository": "my-org/my-repo",
                    "branch": "main",
                    "commit": "abc123",
                },
            )

            assert response.status_code == 202
            data = response.json()
            assert data["execution_id"] == str(mock_execution.id)
            assert "Workflow execution started" in data["message"]

    async def test_webhook_does_not_trigger_disabled_workflow(
        self,
        base_client: AsyncClient,
        eda_workflow: Workflow,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Does not trigger disabled workflows."""
        service = WorkflowService(test_db_session, test_user)
        await service.unpublish_workflow(eda_workflow.id)

        response = await base_client.post(
            "/api/v1/webhooks/eda/github-deployments",
            json={"test": "data"},
        )

        assert response.status_code == 404


class TestEDAWebhookEdgeCases:
    """Edge-case behaviour for the EDA webhook endpoint."""

    @pytest.mark.usefixtures("_no_temporal")
    async def test_webhook_returns_503_when_temporal_unavailable(
        self,
        base_client: AsyncClient,
        eda_workflow: Workflow,
    ) -> None:
        """Returns 503 when Temporal service is unavailable."""
        response = await base_client.post(
            "/api/v1/webhooks/eda/github-deployments",
            json={"test": "data"},
        )

        assert response.status_code == 503

    async def test_webhook_rejects_oversized_payload(
        self,
        base_client: AsyncClient,
    ) -> None:
        """Returns 413 when Content-Length exceeds the payload size limit."""
        response = await base_client.post(
            "/api/v1/webhooks/eda/test-path",
            json={"test": "data"},
            headers={"Content-Length": "2000000"},
        )

        assert response.status_code == 413

    async def test_webhook_does_not_trigger_disabled_trigger_row(
        self,
        base_client: AsyncClient,
        eda_workflow: Workflow,
        test_db_session: AsyncSession,
    ) -> None:
        """Returns 404 when the WebhookTrigger row itself is disabled."""
        result = await test_db_session.exec(select(WebhookTrigger).where(WebhookTrigger.workflow_id == eda_workflow.id))
        trigger = result.one()
        trigger.is_enabled = False
        test_db_session.add(trigger)
        await test_db_session.commit()

        response = await base_client.post(
            "/api/v1/webhooks/eda/github-deployments",
            json={"test": "data"},
        )

        assert response.status_code == 404

    async def test_webhook_does_not_trigger_soft_deleted_workflow(
        self,
        base_client: AsyncClient,
        eda_workflow: Workflow,
        test_db_session: AsyncSession,
    ) -> None:
        """Returns 404 when the owning workflow is soft-deleted."""
        from datetime import UTC, datetime

        eda_workflow.deleted_at = datetime.now(tz=UTC)
        test_db_session.add(eda_workflow)
        await test_db_session.commit()

        response = await base_client.post(
            "/api/v1/webhooks/eda/github-deployments",
            json={"test": "data"},
        )

        assert response.status_code == 404


class TestCrossTypePathIsolation:
    """Verify that webhook_trigger and eda_trigger with the same path are isolated."""

    @pytest_asyncio.fixture
    async def shared_path_workflows(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
    ) -> tuple[Workflow, Workflow]:
        """Create a generic and an EDA workflow sharing the same webhook_path."""
        shared_path = "shared-path"
        service = WorkflowService(test_db_session, test_user)

        wf_a, _v_a, _ = await service.create_workflow(
            name="Generic Webhook Workflow",
            description=None,
            labels={},
            workflow_definition={
                "schema_version": "2.0.0",
                "name": "Generic Webhook Workflow",
                "triggers": [
                    {"id": "wh_1", "type": "webhook_trigger", "parameters": {"webhook_path": shared_path}},
                ],
                "nodes": [
                    {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}},
                ],
                "edges": [{"from": "wh_1", "to": "n1"}],
            },
            project_id=test_project_id,
        )
        wf_a, _v_a, _warning = await service.publish_workflow_version(wf_a.id, version=1)

        wf_b, _v_b, _ = await service.create_workflow(
            name="EDA Webhook Workflow",
            description=None,
            labels={},
            workflow_definition={
                "schema_version": "2.0.0",
                "name": "EDA Webhook Workflow",
                "triggers": [
                    {"id": "eda_1", "type": "eda_trigger", "parameters": {"webhook_path": shared_path}},
                ],
                "nodes": [
                    {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}},
                ],
                "edges": [{"from": "eda_1", "to": "n1"}],
            },
            project_id=test_project_id,
        )
        wf_b, _v_b, _warning = await service.publish_workflow_version(wf_b.id, version=1)

        return wf_a, wf_b

    async def test_eda_endpoint_triggers_eda_workflow_not_generic(
        self,
        temporal_client: AsyncClient,
        shared_path_workflows: tuple[Workflow, Workflow],
    ) -> None:
        """POST /webhooks/eda/shared-path triggers EDA workflow, not generic."""
        _wf_generic, wf_eda = shared_path_workflows

        with patch("syntara.workflows.webhook_router.ExecutionService") as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_execution = Mock(spec=Execution)
            mock_execution.id = uuid4()
            mock_svc.create_execution = AsyncMock(return_value=mock_execution)

            response = await temporal_client.post(
                "/api/v1/webhooks/eda/shared-path",
                json={"event": "deploy"},
            )

            assert response.status_code == 202
            mock_svc.create_execution.assert_called_once()
            call_kwargs = mock_svc.create_execution.call_args[1]
            assert call_kwargs["workflow_id"] == wf_eda.id

    async def test_generic_endpoint_triggers_generic_workflow_not_eda(
        self,
        temporal_client: AsyncClient,
        shared_path_workflows: tuple[Workflow, Workflow],
    ) -> None:
        """POST /webhooks/shared-path triggers generic workflow, not EDA."""
        wf_generic, _wf_eda = shared_path_workflows

        with patch("syntara.workflows.webhook_router.ExecutionService") as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_execution = Mock(spec=Execution)
            mock_execution.id = uuid4()
            mock_svc.create_execution = AsyncMock(return_value=mock_execution)

            response = await temporal_client.post(
                "/api/v1/webhooks/shared-path",
                json={"event": "push"},
            )

            assert response.status_code == 202
            mock_svc.create_execution.assert_called_once()
            call_kwargs = mock_svc.create_execution.call_args[1]
            assert call_kwargs["workflow_id"] == wf_generic.id
