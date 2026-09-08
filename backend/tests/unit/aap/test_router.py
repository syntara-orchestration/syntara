"""Unit tests for AAP router endpoints."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from syntara.aap.audit.aap_resource_access import AAPResourceAccessEvent
from syntara.aap.exceptions import AAPNotConfiguredError
from syntara.aap.models.responses import (
    AAPCredential,
    AAPExecutionEnvironment,
    AAPInstanceGroup,
    AAPInventory,
    AAPJobTemplate,
    AAPJobTemplateDetail,
    AAPLabel,
    AAPListResponse,
    AAPOrganization,
)
from syntara.aap.router import router
from syntara.aap.services.aap_proxy_service import AAPProxyService
from syntara.core.models import User


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create a mock AAPProxyService."""
    service = AsyncMock(spec=AAPProxyService)
    service.close = AsyncMock()
    return service


@pytest.fixture
def mock_user() -> User:
    """Create a mock authenticated user."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    return user


@pytest.fixture
def app(mock_service: AsyncMock, mock_user: User) -> FastAPI:
    """Create a test FastAPI app with AAP router and mocked dependencies."""
    test_app = FastAPI()

    # Override dependencies
    async def mock_get_service() -> AsyncGenerator[AAPProxyService, None]:
        yield mock_service

    async def mock_get_user() -> User:
        return mock_user

    # Apply overrides before including router
    from syntara.aap import router as aap_router
    from syntara.auth import get_current_user

    test_app.dependency_overrides[aap_router._get_aap_proxy_service] = mock_get_service
    test_app.dependency_overrides[get_current_user] = mock_get_user

    test_app.include_router(router, prefix="/api/v1")
    return test_app


class TestListOrganizations:
    """Tests for GET /api/v1/proxies/aap/organizations."""

    @pytest.mark.asyncio
    async def test_returns_organizations(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return list of organizations from service."""
        mock_service.list_organizations.return_value = AAPListResponse(
            count=2,
            results=[
                AAPOrganization(id=1, name="Org 1"),
                AAPOrganization(id=2, name="Org 2"),
            ],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/organizations")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["name"] == "Org 1"
        mock_service.list_organizations.assert_called_once()


class TestListJobTemplates:
    """Tests for GET /api/v1/proxies/aap/job_templates."""

    @pytest.mark.asyncio
    async def test_returns_job_templates(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return list of job templates from service."""
        mock_service.list_job_templates.return_value = AAPListResponse(
            count=1,
            results=[AAPJobTemplate(id=1, name="Template 1", description="Test template")],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/job_templates")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "Template 1"


class TestGetJobTemplate:
    """Tests for GET /api/v1/proxies/aap/job_templates/{job_template_id}."""

    @pytest.mark.asyncio
    async def test_returns_job_template_detail(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return job template details from service."""
        mock_service.get_job_template.return_value = AAPJobTemplateDetail(
            id=1,
            name="Template 1",
            description="Test template",
            ask_credential_on_launch=True,
            ask_inventory_on_launch=False,
            ask_variables_on_launch=True,
            url="https://aap.example.com/templates/1",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/job_templates/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Template 1"
        assert data["ask_credential_on_launch"] is True


class TestListInventories:
    """Tests for GET /api/v1/proxies/aap/inventories."""

    @pytest.mark.asyncio
    async def test_returns_inventories(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return list of inventories from service."""
        mock_service.list_inventories.return_value = AAPListResponse(
            count=1,
            results=[AAPInventory(id=1, name="Inventory 1", description="Test inventory")],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/inventories")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "Inventory 1"


class TestListExecutionEnvironments:
    """Tests for GET /api/v1/proxies/aap/execution_environments."""

    @pytest.mark.asyncio
    async def test_returns_execution_environments(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return list of execution environments from service."""
        mock_service.list_execution_environments.return_value = AAPListResponse(
            count=1,
            results=[AAPExecutionEnvironment(id=1, name="EE 1", description="Test EE")],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/execution_environments")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "EE 1"


class TestListCredentials:
    """Tests for GET /api/v1/proxies/aap/credentials."""

    @pytest.mark.asyncio
    async def test_returns_credentials(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return list of credentials from service."""
        mock_service.list_credentials.return_value = AAPListResponse(
            count=1,
            results=[AAPCredential(id=1, name="Credential 1")],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/credentials")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "Credential 1"


class TestListInstanceGroups:
    """Tests for GET /api/v1/proxies/aap/instance_groups."""

    @pytest.mark.asyncio
    async def test_returns_instance_groups(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return list of instance groups from service."""
        mock_service.list_instance_groups.return_value = AAPListResponse(
            count=1,
            results=[AAPInstanceGroup(id=1, name="Group 1")],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/instance_groups")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "Group 1"


class TestListLabels:
    """Tests for GET /api/v1/proxies/aap/labels."""

    @pytest.mark.asyncio
    async def test_returns_labels(self, app: FastAPI, mock_service: AsyncMock) -> None:
        """Should return list of labels from service."""
        mock_service.list_labels.return_value = AAPListResponse(
            count=2,
            results=[
                AAPLabel(id=1, name="production", organization=1),
                AAPLabel(id=2, name="staging", organization=None),
            ],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/proxies/aap/labels")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["results"][0]["name"] == "production"
        assert data["results"][0]["organization"] == 1
        assert data["results"][1]["name"] == "staging"
        assert data["results"][1]["organization"] is None


class TestCredentialUsedForAudit:
    """Audit credential_used is true only after a credential was resolved."""

    def test_success_is_true(self) -> None:
        from syntara.aap.router import _credential_used_for_audit

        assert _credential_used_for_audit(None) is True

    def test_not_configured_is_false(self) -> None:
        from syntara.aap.router import _credential_used_for_audit

        assert _credential_used_for_audit("AAPNotConfiguredError") is False

    def test_auth_and_upstream_errors_are_true(self) -> None:
        from syntara.aap.router import _credential_used_for_audit

        assert _credential_used_for_audit("AAPAuthenticationError") is True
        assert _credential_used_for_audit("AAPConnectionError") is True
        assert _credential_used_for_audit("AAPUpstreamError") is True

    @pytest.mark.asyncio
    async def test_endpoint_records_false_when_not_configured(
        self, app: FastAPI, mock_service: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """503-before-decrypt must not look credential-backed in audit."""
        captured: list[AAPResourceAccessEvent] = []
        monkeypatch.setattr(
            "syntara.aap.router.AuditEventDispatcher.dispatch",
            captured.append,
        )
        mock_service.list_organizations.side_effect = AAPNotConfiguredError(
            "Multiple AAP Controller integrations are configured; pass integration_id to select one"
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with pytest.raises(AAPNotConfiguredError):
                await client.get("/api/v1/proxies/aap/organizations")

        assert len(captured) == 1
        event = captured[0]
        assert isinstance(event, AAPResourceAccessEvent)
        assert event.credential_used is False
        assert event.error_type == "AAPNotConfiguredError"
