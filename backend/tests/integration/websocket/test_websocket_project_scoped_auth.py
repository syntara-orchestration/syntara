"""Integration tests for WebSocket project-scoped authorization.

Tests verify that WebSocket authorization correctly resolves resource_project
for project-scoped RBAC policies. This is critical for users with permissions
scoped to specific projects (e.g., execution:read on project "ProjectA").

Without resource_project in the AuthzRequest, the authorization engine cannot
evaluate project-scoped policies correctly, causing 403 errors even when the
user should have access.

Run with:
    make -C backend test-integration \
        PYTEST_ARGS="-xvs tests/integration/websocket/test_websocket_project_scoped_auth.py"
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.core.websocket.close_codes import POLICY_VIOLATION
from syntara.core.websocket.connection import get_connection_manager
from syntara.core.websocket.manager import get_connection_lifecycle_manager
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.execution import Execution, ExecutionStatus
from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlmodel.ext.asyncio.session import AsyncSession as _AsyncSession
    from starlette.testclient import TestClient

pytestmark = pytest.mark.integration

EXECUTION_WS_PATH = "/ws/workflows/v1/executions"
INVOCATION_WS_PATH = "/ws/agent_orchestrator/v1/invocations"

_PATCH_AUTHN = "syntara.core.websocket.endpoint_factory._authenticate_websocket"


@pytest.fixture(autouse=True)
def _reset_connection_managers() -> Generator[None, None, None]:
    """Reset connection managers between tests for isolation."""
    manager = get_connection_manager()
    manager.clear_all()
    lifecycle = get_connection_lifecycle_manager()
    lifecycle.clear_all()
    yield
    manager.clear_all()
    lifecycle.clear_all()


_PATCH_FACTORY_DB = "syntara.core.websocket.endpoint_factory.AsyncSessionLocal"


async def _create_execution(
    db: AsyncSession,
    *,
    project_id: UUID,
    created_by: UUID,
) -> Execution:
    """Create a minimal Execution with all required FK rows (Workflow, WorkflowVersion)."""
    workflow = Workflow(
        id=uuid4(),
        name=f"test-workflow-{uuid4().hex[:8]}",
        created_by=created_by,
        project_id=project_id,
    )
    db.add(workflow)
    await db.flush()

    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name=workflow.name),
        created_by=created_by,
    )
    db.add(version)
    await db.flush()

    execution = Execution(
        id=uuid4(),
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        project_id=project_id,
        temporal_workflow_id=f"temporal-{uuid4().hex[:12]}",
        status=ExecutionStatus.RUNNING,
        created_by=created_by,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def _create_invocation(
    db: AsyncSession,
    *,
    project_id: UUID,
    created_by: UUID,
) -> Invocation:
    """Create a minimal Invocation with valid FK references."""
    invocation = Invocation(
        project_id=project_id,
        prompt="test prompt",
        session_id=f"test-session-{uuid4().hex[:8]}",
        created_by=created_by,
    )
    db.add(invocation)
    await db.commit()
    await db.refresh(invocation)
    return invocation


class TestProjectScopedExecutionWebSocketAuthorization:
    """WebSocket authorization must include resource_project for project-scoped policies."""

    @pytest.mark.asyncio
    async def test_websocket_resolves_execution_project_for_authorization(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[_AsyncSession],
        test_user: User,
        test_project_id: UUID,
        sync_test_client: TestClient,
    ) -> None:
        """WebSocket authorization must resolve execution's project and include in AuthzRequest.

        Without resource_project, users with project-scoped execution:read permissions
        get 403 errors even though they should have access.
        """
        project = await test_db_session.get(Project, test_project_id)
        assert project is not None
        project_name = project.name

        execution = await _create_execution(test_db_session, project_id=test_project_id, created_by=test_user.id)

        fake_user = User(
            id=uuid4(),
            username="project-scoped-user",
            email="scoped@example.com",
            first_name="Scoped",
            is_enabled=True,
        )

        captured_authz_request = None

        async def mock_authorize(db, evaluator, authz_request) -> MagicMock:
            nonlocal captured_authz_request
            captured_authz_request = authz_request
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.denied = False
            return mock_result

        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=fake_user)),
            patch("syntara.core.websocket.endpoint_factory.authorize", mock_authorize),
            patch(_PATCH_FACTORY_DB, test_db_session_factory),
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution.id}?ticket=valid") as ws,
        ):
            first_event = ws.receive()
            assert first_event["type"] != "websocket.close" or first_event.get("code") != POLICY_VIOLATION

        assert captured_authz_request is not None, "Authorization was not called"
        assert captured_authz_request.resource_project == project_name, (
            "resource_project must be project NAME for RBAC evaluation"
        )
        assert captured_authz_request.resource_type == "execution"
        assert captured_authz_request.resource_id == str(execution.id)
        assert captured_authz_request.action == "read"

    @pytest.mark.asyncio
    async def test_websocket_rejects_when_execution_not_found(
        self,
        sync_test_client: TestClient,
    ) -> None:
        """WebSocket must reject connections when execution doesn't exist.

        This tests the failure path in project resolution - if we can't find
        the execution or its project, we fail closed.
        """
        non_existent_execution_id = uuid4()

        fake_user = User(
            id=uuid4(),
            username="test-user",
            email="test@example.com",
            first_name="Test",
            is_enabled=True,
        )

        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=fake_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{non_existent_execution_id}?ticket=valid"),
        ):
            pytest.fail("Connection should have been rejected - execution not found")

        assert exc_info.value.code == POLICY_VIOLATION

    @pytest.mark.asyncio
    async def test_websocket_rejects_when_project_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        sync_test_client: TestClient,
    ) -> None:
        """WebSocket must reject when execution's project doesn't exist.

        This tests the edge case where execution.project_id points to a
        non-existent or soft-deleted project.
        """
        execution = await _create_execution(test_db_session, project_id=test_project_id, created_by=test_user.id)

        # Soft-delete the project so the JOIN in resolve_resource_project returns no rows
        project = await test_db_session.get(Project, test_project_id)
        assert project is not None
        from datetime import UTC, datetime

        project.deleted_at = datetime.now(tz=UTC)
        test_db_session.add(project)
        await test_db_session.commit()

        fake_user = User(
            id=uuid4(),
            username="test-user",
            email="test@example.com",
            first_name="Test",
            is_enabled=True,
        )

        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=fake_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution.id}?ticket=valid"),
        ):
            pytest.fail("Connection should have been rejected - project not found")

        assert exc_info.value.code == POLICY_VIOLATION


class TestProjectScopedInvocationWebSocketAuthorization:
    """WebSocket authorization must include resource_project for invocation project-scoped policies."""

    @pytest.mark.asyncio
    async def test_websocket_resolves_invocation_project_for_authorization(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[_AsyncSession],
        test_user: User,
        test_project_id: UUID,
        sync_test_client: TestClient,
    ) -> None:
        """WebSocket authorization must resolve invocation's project and include in AuthzRequest."""
        project = await test_db_session.get(Project, test_project_id)
        assert project is not None
        project_name = project.name

        invocation = await _create_invocation(test_db_session, project_id=test_project_id, created_by=test_user.id)

        fake_user = User(
            id=uuid4(),
            username="project-scoped-user",
            email="scoped@example.com",
            first_name="Scoped",
            is_enabled=True,
        )

        captured_authz_request = None

        async def mock_authorize(db, evaluator, authz_request) -> MagicMock:
            nonlocal captured_authz_request
            captured_authz_request = authz_request
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.denied = False
            return mock_result

        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=fake_user)),
            patch("syntara.core.websocket.endpoint_factory.authorize", mock_authorize),
            patch(_PATCH_FACTORY_DB, test_db_session_factory),
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{invocation.id}?ticket=valid") as ws,
        ):
            first_event = ws.receive()
            assert first_event["type"] != "websocket.close" or first_event.get("code") != POLICY_VIOLATION

        assert captured_authz_request is not None, "Authorization was not called"
        assert captured_authz_request.resource_project == project_name, (
            "resource_project must be project NAME for RBAC evaluation"
        )
        assert captured_authz_request.resource_type == "invocation"
        assert captured_authz_request.resource_id == str(invocation.id)
        assert captured_authz_request.action == "read"

    @pytest.mark.asyncio
    async def test_websocket_rejects_when_invocation_not_found(
        self,
        sync_test_client: TestClient,
    ) -> None:
        """WebSocket must reject connections when invocation doesn't exist."""
        non_existent_invocation_id = uuid4()

        fake_user = User(
            id=uuid4(),
            username="test-user",
            email="test@example.com",
            first_name="Test",
            is_enabled=True,
        )

        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=fake_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{non_existent_invocation_id}?ticket=valid"),
        ):
            pytest.fail("Connection should have been rejected - invocation not found")

        assert exc_info.value.code == POLICY_VIOLATION

    @pytest.mark.asyncio
    async def test_websocket_rejects_when_invocation_project_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        sync_test_client: TestClient,
    ) -> None:
        """WebSocket must reject when invocation's project doesn't exist or is soft-deleted."""
        invocation = await _create_invocation(test_db_session, project_id=test_project_id, created_by=test_user.id)

        # Soft-delete the project so the JOIN returns no rows
        project = await test_db_session.get(Project, test_project_id)
        assert project is not None
        from datetime import UTC, datetime

        project.deleted_at = datetime.now(tz=UTC)
        test_db_session.add(project)
        await test_db_session.commit()

        fake_user = User(
            id=uuid4(),
            username="test-user",
            email="test@example.com",
            first_name="Test",
            is_enabled=True,
        )

        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=fake_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{invocation.id}?ticket=valid"),
        ):
            pytest.fail("Connection should have been rejected - project not found")

        assert exc_info.value.code == POLICY_VIOLATION
