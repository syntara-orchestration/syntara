"""Shared fixtures for integration tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from syntara.authz.models.project import Project
from syntara.integrations.models.integration import (
    IntegrationCreate,
    IntegrationProjectAssignment,
    IntegrationType,
)
from syntara.integrations.services.integration_service import IntegrationService

if TYPE_CHECKING:
    from collections.abc import Generator
    from unittest.mock import MagicMock as MagicMockType

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.integrations.adapters.protocol import DiscoverResult, ValidateResult
    from tests.integration.helpers.credential import CredentialFactory

BASE_URL = "/api/v1/integrations"


# ---------------------------------------------------------------------------
# Service-level fixtures & helpers (used by lifecycle tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_secret_service() -> AsyncMock:
    """Mock SecretService that returns empty decrypted inputs."""
    svc = AsyncMock()
    svc.retrieve_secret = AsyncMock(return_value={})
    return svc


@pytest.fixture
def integration_service(
    test_db_session: AsyncSession, test_user: User, mock_secret_service: AsyncMock
) -> IntegrationService:
    """IntegrationService with a real DB session and mock secret service."""
    return IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)


@pytest_asyncio.fixture
async def llm_credential_id(credential_factory: CredentialFactory) -> UUID:
    """Create an LLM Provider credential with a stored secret and return its ID."""
    from syntara.core.services.secret_service import create_secret_service

    ct = await credential_factory.create_type("LLM Provider")
    project = await credential_factory.create_project()
    cred = await credential_factory.create(ct, project)
    secret_service = create_secret_service(credential_factory.session)
    cred.secret_id = await secret_service.create_secret({"api_key": "sk-test-key"})
    await credential_factory.session.flush()
    return UUID(str(cred.id))


@pytest_asyncio.fixture
async def aap_credential_id(credential_factory: CredentialFactory) -> UUID:
    """Create an AAP credential with a stored secret and return its ID."""
    from syntara.core.services.secret_service import create_secret_service

    ct = await credential_factory.create_type("Ansible Automation Platform")
    project = await credential_factory.create_project()
    cred = await credential_factory.create(ct, project)
    secret_service = create_secret_service(credential_factory.session)
    cred.secret_id = await secret_service.create_secret({"host": "https://gateway.example.com"})
    await credential_factory.session.flush()
    return UUID(str(cred.id))


def make_llm_create(name: str = "My LLM Provider", **kwargs: object) -> IntegrationCreate:
    """Create an IntegrationCreate for an LLM provider with sensible defaults."""
    defaults: dict[str, object] = {
        "name": name,
        "integration_type": IntegrationType.LLM_PROVIDER,
        "configuration": {
            "integration_type": "llm_provider",
            "base_url": "https://api.openai.com",
            "provider_hint": "openai",
        },
    }
    defaults.update(kwargs)
    return IntegrationCreate(**defaults)


def make_mcp_create(name: str = "My MCP Server") -> IntegrationCreate:
    """Create an IntegrationCreate for an MCP server with sensible defaults."""
    return IntegrationCreate(
        name=name,
        integration_type=IntegrationType.MCP_SERVER,
        configuration={"integration_type": "mcp_server", "base_url": "https://mcp.example.com"},
    )


@contextmanager
def mock_adapter(
    *, discover_result: DiscoverResult | None = None, validate_result: ValidateResult | None = None
) -> Generator[MagicMockType]:
    """Patch create_health_check_adapter and get_runtime_settings for lifecycle tests."""
    from unittest.mock import patch

    with (
        patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
        patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
    ):
        mock_settings.return_value.get = AsyncMock(return_value=10)
        adapter = AsyncMock()
        if discover_result is not None:
            adapter.discover = AsyncMock(return_value=discover_result)
        if validate_result is not None:
            adapter.validate = AsyncMock(return_value=validate_result)
        mock_factory.return_value = adapter
        yield adapter


def _mcp_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "integration_type": "mcp_server",
        "configuration": {
            "integration_type": "mcp_server",
            "base_url": "https://mcp.example.com",
        },
    }


@pytest_asyncio.fixture
async def project_scoped_setup(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Set up project-scoped and global integrations, then restrict Rego to one project."""
    project = Project(name=f"test-project-{uuid4().hex[:8]}")
    test_db_session.add(project)
    await test_db_session.flush()

    project_payload = _mcp_payload(f"project-int-{uuid4().hex[:8]}")
    project_payload["scope"] = "project"
    create_resp = await auth_client.post(BASE_URL, json=project_payload)
    assert create_resp.status_code == 201
    project_integration_id = create_resp.json()["id"]

    assignment = IntegrationProjectAssignment(
        integration_id=project_integration_id,
        project_id=project.id,
    )
    test_db_session.add(assignment)

    global_payload = _mcp_payload(f"global-int-{uuid4().hex[:8]}")
    create_resp2 = await auth_client.post(BASE_URL, json=global_payload)
    assert create_resp2.status_code == 201
    global_integration_id = create_resp2.json()["id"]

    unassigned_payload = _mcp_payload(f"unassigned-int-{uuid4().hex[:8]}")
    unassigned_payload["scope"] = "project"
    create_resp3 = await auth_client.post(BASE_URL, json=unassigned_payload)
    assert create_resp3.status_code == 201
    unassigned_integration_id = create_resp3.json()["id"]

    await test_db_session.flush()

    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate = MagicMock(
        return_value={
            "allow": True,
            "deny": False,
            "matched_policy": "test-project-scoped",
            "allowed_projects": [project.name],
        }
    )

    def _mock_getter(request: Any = None) -> AsyncMock:  # noqa: ANN401
        return mock_evaluator

    monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", _mock_getter)
    monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", _mock_getter)

    return {
        "project_id": project.id,
        "project_integration_id": project_integration_id,
        "global_integration_id": global_integration_id,
        "unassigned_integration_id": unassigned_integration_id,
    }
