"""Contract tests for POST /api/v1/integrations/discover.

The discover endpoint tests an unsaved connection and returns a DiscoverResult
with tool information. No integration is persisted.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.integrations.adapters.protocol import DiscoveredTool, DiscoveredToolParameter, DiscoverResult

BASE_URL = "/api/v1/integrations"

MCP_DISCOVER_PATCH = "syntara.integrations.adapters.mcp_server.MCPServerAdapter.discover"


def _fake_discovered_tool(name: str, *, with_params: bool = False) -> DiscoveredTool:
    params = None
    if with_params:
        params = [DiscoveredToolParameter(name="query", type="string", description="Query string", required=True)]
    return DiscoveredTool(name=name, description=f"Description for {name}", parameters=params)


def _mcp_body(credential_id: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "integration_type": "mcp_server",
        "configuration": {
            "integration_type": "mcp_server",
            "base_url": "http://localhost:8080",
        },
    }
    if credential_id is not None:
        body["credential_id"] = credential_id
    return body


def _llm_body(credential_id: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "integration_type": "llm_provider",
        "configuration": {
            "integration_type": "llm_provider",
            "base_url": "http://localhost:11434",
            "provider_hint": "custom",
        },
    }
    if credential_id is not None:
        body["credential_id"] = credential_id
    return body


def _aap_body(credential_id: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "integration_type": "ansible_automation_platform",
        "configuration": {
            "integration_type": "ansible_automation_platform",
            "base_url": "https://gateway.example.com",
        },
    }
    if credential_id is not None:
        body["credential_id"] = credential_id
    return body


@pytest.mark.asyncio
class TestIntegrationDiscoverContract:
    """Contract tests for POST /integrations/discover."""

    @pytest.mark.parametrize(
        "body_fn",
        [_mcp_body, _llm_body, _aap_body],
        ids=["mcp_server", "llm_provider", "aap"],
    )
    async def test_nonexistent_credential_returns_404(
        self, auth_client: AsyncClient, body_fn: Callable[[str], dict[str, object]]
    ) -> None:
        """A credential_id that does not exist returns 404 for any integration type."""
        response = await auth_client.post(
            f"{BASE_URL}/discover",
            json=body_fn(str(uuid4())),
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_invalid_body_missing_fields_returns_422(self, auth_client: AsyncClient) -> None:
        """Request body missing required fields returns 422."""
        response = await auth_client.post(
            f"{BASE_URL}/discover",
            json={"integration_type": "mcp_server"},
        )
        assert response.status_code == 422

    async def test_mismatched_type_and_configuration_returns_422(self, auth_client: AsyncClient) -> None:
        """integration_type and configuration.integration_type mismatch returns 422."""
        response = await auth_client.post(
            f"{BASE_URL}/discover",
            json={
                "integration_type": "mcp_server",
                "configuration": {
                    "integration_type": "llm_provider",
                    "base_url": "http://localhost:11434",
                    "provider_hint": "custom",
                },
                "credential_id": str(uuid4()),
            },
        )
        assert response.status_code == 422

    async def test_unauthenticated_request_returns_401(
        self, base_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Request without authentication returns 401."""
        credential_id = await _create_credential(test_db_session, test_user, "discover-unauth")
        response = await base_client.post(
            f"{BASE_URL}/discover",
            json=_mcp_body(credential_id),
        )
        assert response.status_code == 401

    async def test_successful_discover_returns_discover_result_shape(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Successful discover returns DiscoverResult with expected fields."""
        credential_id = await _create_credential(test_db_session, test_user, "discover-ok")

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[],
        )

        with patch(MCP_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(
                f"{BASE_URL}/discover",
                json=_mcp_body(credential_id),
            )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "checked_at" in data
        assert data["success"] is True
        assert data["discovered_tools"] == [] or data["discovered_tools"] is None

    async def test_successful_discover_returns_tool_list(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Successful discover with tools returns the tool list."""
        credential_id = await _create_credential(test_db_session, test_user, "discover-tools")

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[
                _fake_discovered_tool("tool_a"),
                _fake_discovered_tool("tool_b", with_params=True),
            ],
        )

        with patch(MCP_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(
                f"{BASE_URL}/discover",
                json=_mcp_body(credential_id),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        tools = data["discovered_tools"]
        assert tools is not None
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"tool_a", "tool_b"}

    async def test_successful_discover_tool_with_parameters(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Discovered tools include parameter details when present."""
        credential_id = await _create_credential(test_db_session, test_user, "discover-params")

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[_fake_discovered_tool("search", with_params=True)],
        )

        with patch(MCP_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(
                f"{BASE_URL}/discover",
                json=_mcp_body(credential_id),
            )

        assert response.status_code == 200
        data = response.json()
        tools = data["discovered_tools"]
        assert tools is not None
        assert len(tools) == 1
        params = tools[0]["parameters"]
        assert params is not None
        assert len(params) == 1
        assert params[0]["name"] == "query"
        assert params[0]["type"] == "string"
        assert params[0]["required"] is True

    async def test_failed_discover_returns_200_with_success_false(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """When the adapter returns success=False the endpoint returns 200 with success=False."""
        credential_id = await _create_credential(test_db_session, test_user, "discover-fail")

        discover_result = DiscoverResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Connection refused: simulated failure",
        )

        with patch(MCP_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(
                f"{BASE_URL}/discover",
                json=_mcp_body(credential_id),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data

    async def test_checked_at_is_iso_timestamp(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """checked_at in the response is an ISO 8601 timestamp string."""
        credential_id = await _create_credential(test_db_session, test_user, "discover-ts")

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[],
        )

        with patch(MCP_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(
                f"{BASE_URL}/discover",
                json=_mcp_body(credential_id),
            )

        assert response.status_code == 200
        ts = response.json()["checked_at"]
        assert isinstance(ts, str)
        assert "T" in ts

    async def test_discover_does_not_persist_integration(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """The discover endpoint does not create any Integration records."""
        from sqlmodel import select

        from syntara.integrations.models.integration import Integration

        credential_id = await _create_credential(test_db_session, test_user, "discover-nopersist")

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[_fake_discovered_tool("tool_x")],
        )

        integrations_before = (await test_db_session.exec(select(Integration))).all()

        with patch(MCP_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(
                f"{BASE_URL}/discover",
                json=_mcp_body(credential_id),
            )

        assert response.status_code == 200

        integrations_after = (await test_db_session.exec(select(Integration))).all()
        assert len(integrations_after) == len(integrations_before)

    async def test_mcp_discover_without_credential_succeeds(self, auth_client: AsyncClient) -> None:
        """MCP Server discover without a credential returns 200 (unauthenticated server)."""
        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[_fake_discovered_tool("public_tool")],
        )

        with patch(MCP_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(
                f"{BASE_URL}/discover",
                json={
                    "integration_type": "mcp_server",
                    "configuration": {
                        "integration_type": "mcp_server",
                        "base_url": "https://mcp.example.com",
                    },
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["discovered_tools"]) == 1
        assert data["discovered_tools"][0]["name"] == "public_tool"

    async def test_llm_discover_without_credential_returns_422(self, auth_client: AsyncClient) -> None:
        """LLM provider discover without credential_id returns 422."""
        response = await auth_client.post(f"{BASE_URL}/discover", json=_llm_body())
        assert response.status_code == 422

    async def test_aap_discover_without_credential_returns_422(self, auth_client: AsyncClient) -> None:
        """AAP discover without credential_id returns 422."""
        response = await auth_client.post(f"{BASE_URL}/discover", json=_aap_body())
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_credential(
    session: AsyncSession,
    user: User,
    name_prefix: str,
) -> str:
    """Create a minimal credential for use in discover request bodies."""
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
    await session.commit()

    return str(credential.id)
