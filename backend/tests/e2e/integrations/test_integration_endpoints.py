"""E2E tests for integration API endpoints.

Covers CRUD operations for all three integration types (MCP server,
LLM provider, Ansible Automation Platform), filtering, pagination, and error cases.

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.fixtures import MCP_PROVIDER_URL
from syntara_api_client.models.aap_configuration import AAPConfiguration
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs
from syntara_api_client.models.integration_create import IntegrationCreate
from syntara_api_client.models.integration_type import IntegrationType
from syntara_api_client.models.integration_update import IntegrationUpdate
from syntara_api_client.models.llm_provider_configuration import LLMProviderConfiguration
from syntara_api_client.models.llm_provider_hint import LLMProviderHint
from syntara_api_client.models.mcp_server_configuration_input import MCPServerConfigurationInput

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _find_credential_type_id(syntara_api: SyntaraApiRegistry, name_fragment: str) -> UUID:
    """Find a credential type ID by partial name match."""
    types_list = syntara_api.credentials.list_types().assert_and_get()
    for ct in types_list.resources:
        if name_fragment.lower() in ct.name.lower():
            return UUID(str(ct.id))
    msg = f"Credential type matching '{name_fragment}' not found — is the database seeded?"
    raise AssertionError(msg)


def _create_credential(
    syntara_api: SyntaraApiRegistry,
    type_name_fragment: str,
    project_id: UUID,
    inputs: dict[str, str],
) -> UUID:
    """Create a credential via the API and return its UUID."""
    type_id = _find_credential_type_id(syntara_api, type_name_fragment)
    cred = syntara_api.credentials.create(
        body=CredentialCreate(
            name=unique_name(f"e2e-cred-{type_name_fragment.lower().replace(' ', '-')}"),
            credential_type_id=type_id,
            project_id=project_id,
            inputs=CredentialCreateInputs.from_dict(inputs),
        ),
    ).assert_and_get()
    return UUID(str(cred.id))


@pytest.fixture
def e2e_llm_credential_id(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> Generator[UUID, None, None]:
    """Create an LLM Provider credential for integration e2e tests."""
    cred_id = _create_credential(syntara_api, "LLM Provider", first_project_id, {"api_key": "test-key"})
    yield cred_id
    try:
        syntara_api.credentials.delete(credential_id=cred_id)
    except Exception:
        pass


@pytest.fixture
def e2e_aap_credential_id(syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> Generator[UUID, None, None]:
    """Create an AAP credential for integration e2e tests."""
    cred_id = _create_credential(
        syntara_api,
        "Ansible Automation Platform",
        first_project_id,
        {"oauth_token": "test-token"},
    )
    yield cred_id
    try:
        syntara_api.credentials.delete(credential_id=cred_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Integration create helpers
# ---------------------------------------------------------------------------


def _mcp_create(name: str | None = None) -> IntegrationCreate:
    return IntegrationCreate(
        name=name or unique_name("e2e-mcp"),
        integration_type=IntegrationType.MCP_SERVER,
        configuration=MCPServerConfigurationInput(base_url="https://mcp.example.com"),
    )


def _llm_create(name: str | None = None, management_credential_id: UUID | None = None) -> IntegrationCreate:
    return IntegrationCreate(
        name=name or unique_name("e2e-llm"),
        integration_type=IntegrationType.LLM_PROVIDER,
        configuration=LLMProviderConfiguration(
            base_url="https://api.openai.com",
            provider_hint=LLMProviderHint.OPENAI,
        ),
        management_credential_id=management_credential_id,
    )


def _aap_create(name: str | None = None, management_credential_id: UUID | None = None) -> IntegrationCreate:
    return IntegrationCreate(
        name=name or unique_name("e2e-aap"),
        integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
        configuration=AAPConfiguration(
            base_url="https://gateway.example.com",
            insecure_skip_tls_verify=False,
        ),
        management_credential_id=management_credential_id,
    )


class TestCreateIntegration:
    """POST /api/v1/integrations."""

    def test_create_mcp_server(self, integration_factory: Callable[..., dict[str, Any]]) -> None:
        result = integration_factory(_mcp_create())
        assert result["integration_type"] == "mcp_server"
        assert result["configuration"]["base_url"] == "https://mcp.example.com"
        assert result["validation_status"] == "unknown"
        assert result["enabled"] is True
        assert result["scope"] == "global"

    def test_create_llm_provider(
        self, integration_factory: Callable[..., dict[str, Any]], e2e_llm_credential_id: UUID
    ) -> None:
        result = integration_factory(_llm_create(management_credential_id=e2e_llm_credential_id))
        assert result["integration_type"] == "llm_provider"
        assert result["configuration"]["provider_hint"] == "openai"

    def test_create_aap(self, integration_factory: Callable[..., dict[str, Any]], e2e_aap_credential_id: UUID) -> None:
        result = integration_factory(_aap_create(management_credential_id=e2e_aap_credential_id))
        assert result["integration_type"] == "ansible_automation_platform"
        assert result["configuration"]["insecure_skip_tls_verify"] is False

    def test_create_llm_without_credential_returns_422(self, syntara_api: SyntaraApiRegistry) -> None:
        resp = syntara_api.integrations.create(body=_llm_create())
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_create_aap_without_credential_returns_422(self, syntara_api: SyntaraApiRegistry) -> None:
        resp = syntara_api.integrations.create(body=_aap_create())
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_create_duplicate_name_returns_409(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        name = unique_name("e2e-dup")
        integration_factory(_mcp_create(name=name))
        resp = syntara_api.integrations.create(body=_mcp_create(name=name))
        assert resp.status_code == HTTPStatus.CONFLICT


class TestGetIntegration:
    """GET /api/v1/integrations/{integration_id}."""

    def test_get_returns_200(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        created = integration_factory(_mcp_create())
        integration = syntara_api.integrations.get(integration_id=UUID(created["id"])).assert_and_get()
        assert str(integration.id) == created["id"]

    def test_get_not_found_returns_404(self, syntara_api: SyntaraApiRegistry) -> None:
        resp = syntara_api.integrations.get(integration_id=uuid4())
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestListIntegrations:
    """GET /api/v1/integrations."""

    def test_list_returns_created(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        created = integration_factory(_mcp_create())
        result = syntara_api.integrations.list().assert_and_get()
        ids = [str(r.id) for r in result.resources]
        assert created["id"] in ids

    def test_list_filter_by_type(
        self,
        syntara_api: SyntaraApiRegistry,
        integration_factory: Callable[..., dict[str, Any]],
        e2e_llm_credential_id: UUID,
    ) -> None:
        integration_factory(_mcp_create())
        integration_factory(_llm_create(management_credential_id=e2e_llm_credential_id))
        result = syntara_api.integrations.list(integration_type=IntegrationType.MCP_SERVER).assert_and_get()
        for r in result.resources:
            assert r.integration_type == IntegrationType.MCP_SERVER

    def test_list_filter_by_enabled(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        integration_factory(
            IntegrationCreate(
                name=unique_name("e2e-disabled"),
                integration_type=IntegrationType.MCP_SERVER,
                configuration=MCPServerConfigurationInput(base_url="https://mcp.example.com"),
                enabled=False,
            )
        )
        result = syntara_api.integrations.list(enabled=False).assert_and_get()
        for r in result.resources:
            assert r.enabled is False

    def test_list_pagination(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        for _ in range(3):
            integration_factory(_mcp_create())
        result = syntara_api.integrations.list(limit=2).assert_and_get()
        assert len(result.resources) == 2
        assert result.next_ is not None


class TestPatchIntegration:
    """PATCH /api/v1/integrations/{integration_id}."""

    def test_patch_name(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        created = integration_factory(_mcp_create())
        new_name = unique_name("e2e-renamed")
        updated = syntara_api.integrations.update(
            integration_id=UUID(created["id"]),
            body=IntegrationUpdate(name=new_name),
        ).assert_and_get()
        assert updated.name == new_name

    def test_patch_enabled(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        created = integration_factory(_mcp_create())
        updated = syntara_api.integrations.update(
            integration_id=UUID(created["id"]),
            body=IntegrationUpdate(enabled=False),
        ).assert_and_get()
        assert updated.enabled is False

    def test_patch_name_conflict_returns_409(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        taken_name = unique_name("e2e-taken")
        integration_factory(_mcp_create(name=taken_name))
        other = integration_factory(_mcp_create())
        resp = syntara_api.integrations.update(
            integration_id=UUID(other["id"]),
            body=IntegrationUpdate(name=taken_name),
        )
        assert resp.status_code == HTTPStatus.CONFLICT

    def test_patch_config_type_mismatch_returns_422(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        created = integration_factory(_mcp_create())
        resp = syntara_api.integrations.update(
            integration_id=UUID(created["id"]),
            body=IntegrationUpdate(
                configuration=LLMProviderConfiguration(
                    base_url="https://api.openai.com", provider_hint=LLMProviderHint.OPENAI
                ),
            ),
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestDeleteIntegration:
    """DELETE /api/v1/integrations/{integration_id}."""

    def test_delete_returns_204(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        created = integration_factory(_mcp_create())
        integration_id = UUID(created["id"])
        resp = syntara_api.integrations.delete(integration_id=integration_id)
        assert resp.status_code == HTTPStatus.NO_CONTENT

    def test_delete_not_found_returns_404(self, syntara_api: SyntaraApiRegistry) -> None:
        resp = syntara_api.integrations.delete(integration_id=uuid4())
        assert resp.status_code == HTTPStatus.NOT_FOUND

    def test_deleted_not_gettable(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        created = integration_factory(_mcp_create())
        integration_id = UUID(created["id"])
        syntara_api.integrations.delete(integration_id=integration_id)
        resp = syntara_api.integrations.get(integration_id=integration_id)
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestValidateIntegration:
    """Tests for POST /integrations/{id}/validate."""

    def test_validate_nonexistent_returns_404(self, syntara_api: SyntaraApiRegistry) -> None:
        resp = syntara_api.integrations.validate(integration_id=uuid4())
        assert resp.status_code == HTTPStatus.NOT_FOUND

    def test_validate_unreachable_server_returns_200_with_connection_error(
        self, syntara_api: SyntaraApiRegistry, integration_factory: Callable[..., dict[str, Any]]
    ) -> None:
        """Validate returns 200 OK with success=False and connection_error/timeout when MCP server is unreachable.

        The integration is properly configured (valid URL, no credential required),
        but the external MCP server at https://mcp.example.com does not exist.
        This is not a client error (4xx) — the request is valid. It's an external
        service failure, communicated via the success/error/error_type fields in the response.
        """
        created = integration_factory(_mcp_create())
        integration_id = UUID(created["id"])
        resp = syntara_api.integrations.validate(integration_id=integration_id)

        # HTTP 200 OK — the API request itself succeeded
        assert resp.status_code == HTTPStatus.OK

        # But validation failed because the external MCP server is unreachable
        result = resp.assert_and_get()
        assert result.success is False
        assert result.error is not None
        assert result.error_type in ["connection_error", "timeout"]

    @pytest.mark.mcp
    def test_validate_success_against_real_mcp_server(
        self,
        syntara_api: SyntaraApiRegistry,
        integration_factory: Callable[..., dict[str, Any]],
        mcp_integration_id: str,
    ) -> None:
        """Validate performs real MCP ping against test server — succeeds and returns success=True."""
        created = integration_factory(
            IntegrationCreate(
                name=unique_name("e2e-mcp-real"),
                integration_type=IntegrationType.MCP_SERVER,
                configuration=MCPServerConfigurationInput(base_url=MCP_PROVIDER_URL, allow_http=True),
            )
        )
        integration_id = UUID(created["id"])
        resp = syntara_api.integrations.validate(integration_id=integration_id)

        # Validate endpoint returns 200 with successful ping result
        assert resp.status_code == HTTPStatus.OK

        result = resp.assert_and_get()
        assert result.success is True
        assert result.error is None
        assert result.error_type is None
        assert result.checked_at is not None
