"""Contract tests for POST /api/v1/integrations/{integration_id}/validate.

The validate endpoint now performs a lightweight connectivity ping only —
no tool sync.  It returns a ValidateResult (success, checked_at, error,
error_type) and updates Integration.status to AVAILABLE or ERROR.
Tool sync is handled by the separate /refresh endpoint.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.integrations.adapters.protocol import ValidateResult
from syntara.integrations.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationStatus,
    IntegrationType,
)
from syntara.integrations.services.integration_service import IntegrationService

BASE_URL = "/api/v1/integrations"

MCP_VALIDATE_PATCH = "syntara.integrations.adapters.mcp_server.MCPServerAdapter.validate"


@pytest.mark.asyncio
class TestIntegrationValidateContract:
    """Contract tests for POST /integrations/{id}/validate."""

    async def test_validate_not_found_returns_404(self, auth_client: AsyncClient) -> None:
        """Non-existent integration returns 404."""
        response = await auth_client.post(f"{BASE_URL}/{uuid4()}/validate")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data or "error" in data

    async def test_validate_invalid_uuid_returns_422(self, auth_client: AsyncClient) -> None:
        """Invalid UUID in path returns 422."""
        response = await auth_client.post(f"{BASE_URL}/not-a-uuid/validate")
        assert response.status_code == 422

    async def test_validate_without_credential_returns_200(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Integration with no management_credential_id returns 200 with validation result.

        Validate performs a real MCP SDK ping. For a non-existent server (localhost:8080),
        the ping will fail with CONNECTION_ERROR or TIMEOUT, but the endpoint still returns
        200 OK with the validation result (success=False, error populated).
        """
        service = IntegrationService(test_db_session, test_user)
        created = await service.create_integration(
            IntegrationCreate(
                name=f"validate-nocred-{uuid4().hex[:8]}",
                integration_type=IntegrationType.MCP_SERVER,
                configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
            )
        )
        await test_db_session.commit()

        response = await auth_client.post(f"{BASE_URL}/{created.id}/validate")
        assert response.status_code == 200

        # Validation result should indicate failure for non-existent server
        result = response.json()
        assert result["success"] is False
        assert result["error"] is not None
        assert result["error_type"] in ["connection_error", "timeout"]

    async def test_validate_success_returns_validate_result_fields(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Successful validation returns ValidateResult with required fields."""
        integration_id = await _create_integration_with_mocked_credential(test_db_session, test_user, "validate-ok")

        success_result = ValidateResult(
            success=True,
            checked_at=datetime.now(UTC),
        )

        with patch(MCP_VALIDATE_PATCH, new=AsyncMock(return_value=success_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "checked_at" in data
        assert data["success"] is True
        # ValidateResult does NOT include tool sync counts or discovered_tools
        assert "tools_refreshed_count" not in data
        assert "discovered_tools" not in data

    async def test_validate_success_updates_status_to_available(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """A passing ping transitions Integration.status to AVAILABLE."""
        integration_id = await _create_integration_with_mocked_credential(
            test_db_session, test_user, "validate-status-ok"
        )

        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with patch(MCP_VALIDATE_PATCH, new=AsyncMock(return_value=success_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 200

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["validation_status"] == IntegrationStatus.AVAILABLE.value

    async def test_validate_failure_updates_status_to_error(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """A failing ping transitions Integration.status to ERROR and persists validation_error."""
        integration_id = await _create_integration_with_mocked_credential(
            test_db_session, test_user, "validate-status-err"
        )

        error_result = ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Connection refused: simulated failure",
        )

        with patch(MCP_VALIDATE_PATCH, new=AsyncMock(return_value=error_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 200
        assert response.json()["success"] is False

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert get_resp.status_code == 200
        integration_data = get_resp.json()
        assert integration_data["validation_status"] == IntegrationStatus.ERROR.value
        assert "Connection refused" in (integration_data.get("validation_error") or "")

    async def test_validate_sets_last_validated_at(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """last_validated_at is populated after a validate call."""
        integration_id = await _create_integration_with_mocked_credential(test_db_session, test_user, "validate-ts")

        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with patch(MCP_VALIDATE_PATCH, new=AsyncMock(return_value=success_result)):
            await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert get_resp.status_code == 200
        ts = get_resp.json().get("last_validated_at")
        assert ts is not None
        assert "T" in ts  # ISO 8601 separator

    async def test_validate_checked_at_is_iso_timestamp(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """checked_at in the response is an ISO 8601 timestamp string."""
        integration_id = await _create_integration_with_mocked_credential(
            test_db_session, test_user, "validate-checked-at"
        )

        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with patch(MCP_VALIDATE_PATCH, new=AsyncMock(return_value=success_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 200
        ts = response.json()["checked_at"]
        assert isinstance(ts, str)
        assert "T" in ts

    async def test_validate_does_not_sync_tools(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Validate does NOT sync Tool records — that is the refresh endpoint's job."""
        from sqlmodel import select

        from syntara.tool_manager.models.tool import Tool

        integration_id = await _create_integration_with_mocked_credential(
            test_db_session, test_user, "validate-no-sync"
        )
        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with patch(MCP_VALIDATE_PATCH, new=AsyncMock(return_value=success_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 200

        # No Tool records should have been created
        tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == integration_id))).all()
        assert len(tools) == 0

    async def test_validate_persists_error_when_commit_aborts(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """A DB failure while persisting validation success leaves ERROR recorded.

        validate_integration's unexpected-error handler must roll back the session
        before persisting ERROR state. Without rollback, _get_or_raise raises
        PendingRollbackError and validation_error is never written — the integration
        stays validation_status=VALIDATING with validation_error=null.
        """
        integration_id = await _create_integration_with_mocked_credential(test_db_session, test_user, "validate-wedge")

        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))
        real_commit = test_db_session.commit
        commit_calls = 0

        async def commit_side_effect(*args: object, **kwargs: object) -> None:
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 2:
                statement = "UPDATE integrations SET validation_status"
                orig = Exception("simulated constraint violation")
                raise IntegrityError(statement, {}, orig)
            await real_commit(*args, **kwargs)

        with (
            patch(MCP_VALIDATE_PATCH, new=AsyncMock(return_value=success_result)),
            patch.object(test_db_session, "commit", side_effect=commit_side_effect),
        ):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 400

        test_db_session.expire_all()
        refreshed = await test_db_session.get(Integration, UUID(integration_id))
        assert refreshed is not None
        assert refreshed.validation_status == IntegrationStatus.ERROR
        assert refreshed.validation_error is not None
        assert "IntegrityError" in refreshed.validation_error
        assert refreshed.last_validated_at is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_integration_with_mocked_credential(
    session: AsyncSession,
    user: User,
    name_prefix: str,
) -> str:
    """Create an mcp_server integration with a minimal fake credential attached."""
    from sqlmodel import select as sql_select

    from syntara.authz.models import Project
    from syntara.core.services.secret_service import create_secret_service

    project = Project(name=f"{name_prefix}-proj-{uuid4().hex[:8]}")
    session.add(project)
    await session.flush()

    cred_type = (
        await session.exec(sql_select(CredentialType).where(CredentialType.name == "HTTP Bearer Token"))
    ).one_or_none()
    if not cred_type:
        cred_type = CredentialType(
            name="HTTP Bearer Token",
            description="Bearer token",
            inputs={
                "fields": [{"id": "token", "type": "string", "secret": True, "label": "Token"}],
                "required": ["token"],
            },
            injectors={"extra_vars": {"bearer_token": "{{token}}"}},
            managed=True,
        )
        session.add(cred_type)
        await session.flush()

    secret_service = create_secret_service(session)
    secret_id = await secret_service.create_secret({"token": "test-bearer-token"})

    credential = Credential(
        name=f"{name_prefix}-cred-{uuid4().hex[:8]}",
        credential_type_id=cred_type.id,
        secret_id=secret_id,
        enabled=True,
        project_id=project.id,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(credential)
    await session.flush()

    service = IntegrationService(session, user)
    created = await service.create_integration(
        IntegrationCreate(
            name=f"{name_prefix}-{uuid4().hex[:8]}",
            integration_type=IntegrationType.MCP_SERVER,
            configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
            management_credential_id=credential.id,
        )
    )
    await session.commit()
    return str(created.id)
