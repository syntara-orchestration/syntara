"""Pytest fixtures for Syntara E2E tests.

All fixtures in this module are intended to be imported into a project's
``tests/e2e/conftest.py`` so they apply to tests under that directory tree.
"""

from __future__ import annotations

import logging
import os
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import httpx
import pytest
from syntara_api_client import AuthenticatedClient
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs
from syntara_api_client.models.initial_model_selection import InitialModelSelection
from syntara_api_client.models.integration_create import IntegrationCreate
from syntara_api_client.models.integration_refresh_status import IntegrationRefreshStatus
from syntara_api_client.models.integration_type import IntegrationType
from syntara_api_client.models.integration_update import IntegrationUpdate
from syntara_api_client.models.llm_provider_configuration import LLMProviderConfiguration
from syntara_api_client.models.llm_provider_hint import LLMProviderHint
from syntara_api_client.models.mcp_server_configuration_input import MCPServerConfigurationInput
from syntara_api_client.models.sub_resource_role_assignment_create import SubResourceRoleAssignmentCreate
from syntara_api_client.models.user_create import UserCreate
from syntara_api_client.types import UNSET, Unset
from typer.testing import CliRunner

from orchestrator_test_sdk.e2e import generate_test_password, unique_name
from orchestrator_test_sdk.e2e.auth import (
    _AutoRefreshAuth,
    _generate_e2e_token,
    _login,
)
from orchestrator_test_sdk.e2e.helpers import (
    get_first_non_builtin_project_id,
)
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from click.testing import Result
    from syntara_api_client.models import (
        WorkflowCreate,
        WorkflowRead,
    )
    from syntara_api_client.models.user_info import UserInfo
    from syntara_api_client.models.user_read import UserRead

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP constants
# ---------------------------------------------------------------------------

MCP_PROVIDER_NAME = "mcp"
MCP_PORT = os.environ.get("MCP_PORT", "8765")
MCP_PROVIDER_URL = os.environ.get("MCP_BASE_URL", f"http://mcp-server:{MCP_PORT}/mcp")
MCP_HEALTH_URL = f"http://localhost:{MCP_PORT}/health"

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_API_HEALTH_TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Core client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def auth_headers(syntara_base_url: str) -> dict[str, str]:
    """Return Bearer auth headers for raw httpx calls."""
    token = _generate_e2e_token(syntara_base_url)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def syntara_client(syntara_base_url: str) -> AuthenticatedClient:
    """Return an authenticated Syntara API client connected to the test environment."""
    base_url = syntara_base_url

    try:
        response = httpx.get(f"{base_url}/health", timeout=5, verify=e2e_ssl_context())
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        pytest.exit(
            f"Environment not available at {base_url}: {exc}\n"
            "Start the services first with: make services-run && make dev",
            returncode=1,
        )

    access_token = _generate_e2e_token(base_url)

    return AuthenticatedClient(
        base_url=f"{base_url}/api/v1",
        token=access_token,
        verify_ssl=e2e_ssl_context(),
        timeout=httpx.Timeout(60.0),
        httpx_args={"auth": _AutoRefreshAuth(base_url, access_token)},
    )


@pytest.fixture(scope="session")
def syntara_api(syntara_client: AuthenticatedClient) -> SyntaraApiRegistry:
    """Return a SyntaraApiRegistry bound to the session-scoped authenticated client.

    Uses ``syntara_client``, which refreshes the admin JWT via ``_AutoRefreshAuth`` on
    expiry or 401. Authentication E2E tests that revoke user/IdP sessions should use
    this fixture for admin API calls; those revocations do not invalidate unrelated
    admin tokens.
    """
    return SyntaraApiRegistry(syntara_client)


@pytest.fixture(scope="session")
def unauthenticated_client(syntara_base_url: str) -> AuthenticatedClient:
    """Return an unauthenticated Syntara API client for login flows and public endpoints.

    Uses an invalid token so requests are rejected with 401 by protected endpoints.
    SSL verification is disabled for E2E tests (localhost/test environment with
    self-signed certs). This is acceptable for test code but should NEVER be
    used in production.
    """
    return AuthenticatedClient(
        base_url=f"{syntara_base_url}/api/v1",
        token="unauthenticated",  # noqa: S106
        verify_ssl=e2e_ssl_context(),
    )


@pytest.fixture
def unauth_api(syntara_base_url: str, unauthenticated_client: AuthenticatedClient) -> SyntaraApiRegistry:
    """SyntaraApiRegistry backed by a client with no valid auth token.

    Used to verify that unauthenticated requests are rejected with 401.
    SSL verification is disabled for E2E tests (localhost/test environment with
    self-signed certs). This is acceptable for test code but should NEVER be
    used in production.
    """
    return SyntaraApiRegistry(unauthenticated_client)


@pytest.fixture(autouse=True)
def reset_async_client(syntara_client: AuthenticatedClient) -> Generator[None, None, None]:
    """Reset the cached async httpx client between tests.

    syntara_client is session-scoped but async tests run with function-scoped event loops.
    Without this, the AsyncClient created in one test's loop becomes stale for the next.
    Token refresh is handled transparently by _AutoRefreshAuth on every request.
    """
    yield
    syntara_client._async_client = None  # noqa: SLF001


@pytest.fixture(autouse=True)
def _wait_for_api(syntara_api: SyntaraApiRegistry) -> None:
    """Wait for the API to be healthy before each test.

    The database can become temporarily unreachable in the KinD CI cluster,
    causing cascading 500s. This fixture ensures the API is responsive before
    each test starts, absorbing any recovery window from prior tests.
    """
    deadline = time.monotonic() + _API_HEALTH_TIMEOUT
    while True:
        try:
            resp = syntara_api.settings.list(limit=1)
            if resp.status_code == HTTPStatus.OK:
                return
        except Exception:
            pass
        if time.monotonic() >= deadline:
            pytest.fail(f"API not healthy after {_API_HEALTH_TIMEOUT}s")
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Role-scoped client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def viewer_client(syntara_base_url: str, syntara_api: SyntaraApiRegistry) -> AuthenticatedClient:
    """Return an authenticated client for a non-admin (viewer) user.

    Creates the user via the admin client on first use.  The user has no
    role assignments, so all permission-gated endpoints should deny access.
    """
    username = "e2e-viewer"
    password = "ViewerPass1234!"  # noqa: S105

    resp = syntara_api.users.create(
        body=UserCreate(
            username=username,
            email="e2e-viewer@example.com",
            first_name="E2E Viewer",
            password=password,
        ),
    )
    if resp.status_code not in (HTTPStatus.CREATED, HTTPStatus.CONFLICT):
        pytest.fail(f"Failed to create viewer user: {resp.status_code} {resp.content!r}")

    token = _login(syntara_base_url, username, password)
    return AuthenticatedClient(
        base_url=f"{syntara_base_url}/api/v1",
        token=token,
        verify_ssl=e2e_ssl_context(),
        timeout=httpx.Timeout(60.0),
        httpx_args={"auth": _AutoRefreshAuth(syntara_base_url, token, username=username, password=password)},
    )


@pytest.fixture(scope="session")
def viewer_api(viewer_client: AuthenticatedClient) -> SyntaraApiRegistry:
    """Return a SyntaraApiRegistry bound to the non-admin viewer client."""
    return SyntaraApiRegistry(viewer_client)


@pytest.fixture(scope="session")
def auditor_client(syntara_base_url: str, syntara_api: SyntaraApiRegistry) -> AuthenticatedClient:
    """Return an authenticated client for a user with the auditor role.

    Creates the user and assigns the auditor role via the generated API
    client on first use.  The user has read-only access to most resources
    including settings, but cannot perform write operations.
    """
    username = "e2e-auditor"
    password = "AuditorPass1234!"  # noqa: S105

    resp = syntara_api.users.create(
        body=UserCreate(
            username=username,
            email="e2e-auditor@example.com",
            first_name="E2E Auditor",
            password=password,
        ),
    )
    if resp.status_code not in (HTTPStatus.CREATED, HTTPStatus.CONFLICT):
        pytest.fail(f"Failed to create auditor user: {resp.status_code} {resp.content!r}")

    if resp.status_code == HTTPStatus.CONFLICT:
        users_list = syntara_api.users.list(username=username).assert_and_get()
        user_id = users_list.resources[0].id
    else:
        user = resp.assert_and_get()
        user_id = user.id

    role_resp = syntara_api.users.create_role_assignment(
        user_id=user_id,
        body=SubResourceRoleAssignmentCreate(role_name="auditor"),
    )
    if role_resp.status_code not in (
        HTTPStatus.CREATED,
        HTTPStatus.CONFLICT,
        HTTPStatus.UNPROCESSABLE_ENTITY,  # role already assigned
    ):
        pytest.fail(f"Failed to assign auditor role: {role_resp.status_code} {role_resp.content!r}")

    token = _login(syntara_base_url, username, password)
    return AuthenticatedClient(
        base_url=f"{syntara_base_url}/api/v1",
        token=token,
        verify_ssl=e2e_ssl_context(),
        timeout=httpx.Timeout(60.0),
        httpx_args={"auth": _AutoRefreshAuth(syntara_base_url, token, username=username, password=password)},
    )


@pytest.fixture(scope="session")
def auditor_api(auditor_client: AuthenticatedClient) -> SyntaraApiRegistry:
    """Return a SyntaraApiRegistry bound to the auditor client."""
    return SyntaraApiRegistry(auditor_client)


# ---------------------------------------------------------------------------
# Infrastructure / environment fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def worker_base_url() -> str:
    """Return the URL the Temporal worker uses to reach the Syntara API.

    The worker runs inside a container, so it cannot use localhost or the
    syntara_base_url (which is host-side).  The default uses the podman host
    gateway so the containerised worker can reach the API process running on
    the host.  Override with APP_WORKER_BASE_URL in CI or other environments.
    """
    return os.environ.get("APP_WORKER_BASE_URL", "http://host.containers.internal:8000")


# ---------------------------------------------------------------------------
# Admin / group / integration fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def syntara_api_admin_group_id(syntara_api: SyntaraApiRegistry) -> UUID:
    """Get admin role group ID."""
    groups_resp = syntara_api.groups.list(additional_params={"name": "admins"}, limit=100)
    if groups_resp.parsed is None or len(groups_resp.parsed.resources) == 0:
        msg = "Unable to retrieve admin group ID."
        raise RuntimeError(msg)
    groups_list = groups_resp.assert_and_get()
    admins_group_id = [g.id for g in groups_list.resources if g.name == "admins"]
    if len(admins_group_id) != 1:
        msg = "Unable to retrieve admin group ID."
        raise RuntimeError(msg)
    return cast("UUID", admins_group_id[0])


@pytest.fixture(scope="session")
def require_mcp_server() -> None:
    """Skip the test unless the bundled MCP test server is deployed in this environment.

    Health-checks ``MCP_HEALTH_URL`` and skips on failure. Reachability here is the
    signal for "the MCP test infra is present", which in every environment that
    provisions it (podman-compose, CI) coincides with ``mcp-server`` being in
    ``APP_INTEGRATION_URL_ALLOWED_HOSTS``. Deployments without the test server (e.g. the
    AAP/AO environment) leave that allowlist at its empty default, so tests that need an
    allowlisted-but-unreachable host would otherwise fail the write-time SSRF check with
    422. Depend on this fixture (and mark the test ``@pytest.mark.mcp``) to skip cleanly
    there, matching how the rest of the MCP-dependent suite behaves.
    """
    try:
        resp = httpx.get(MCP_HEALTH_URL, timeout=5, verify=e2e_ssl_context())
        resp.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        pytest.skip(f"MCP server not reachable at {MCP_HEALTH_URL}: {exc}")


@pytest.fixture(scope="session")
def mcp_integration_id(syntara_api: SyntaraApiRegistry, require_mcp_server: None) -> str:
    """Return the ID of the shared MCP server Integration used by E2E tests.

    Skips (via ``require_mcp_server``) when the MCP server is unreachable, then either
    finds an existing Integration named MCP_PROVIDER_NAME or creates one.  Both validate
    and refresh_resources are synchronous — status is final when they return.
    """
    integrations_resp = syntara_api.integrations.list(integration_type=IntegrationType.MCP_SERVER)
    integrations_list = integrations_resp.assert_and_get()

    existing = next(
        (i for i in integrations_list.resources if i.name == MCP_PROVIDER_NAME),
        None,
    )

    if existing is not None:
        integration_id = str(existing.id)
        syntara_api.integrations.update(
            integration_id=UUID(integration_id),
            body=IntegrationUpdate(
                configuration=MCPServerConfigurationInput(base_url=MCP_PROVIDER_URL, allow_http=True),
            ),
        )
    else:
        create_resp = syntara_api.integrations.create(
            body=IntegrationCreate(
                name=MCP_PROVIDER_NAME,
                description="MCP server for E2E tests",
                integration_type=IntegrationType.MCP_SERVER,
                configuration=MCPServerConfigurationInput(base_url=MCP_PROVIDER_URL, allow_http=True),
            )
        )
        integration = create_resp.assert_and_get()
        integration_id = str(integration.id)

    syntara_api.integrations.validate(integration_id=UUID(integration_id))
    syntara_api.integrations.refresh_resources(integration_id=UUID(integration_id))

    integration = syntara_api.integrations.get(integration_id=UUID(integration_id)).assert_and_get()
    if integration.refresh_status != IntegrationRefreshStatus.AVAILABLE:
        pytest.fail(
            f"MCP integration {integration_id} refresh failed: "
            f"status={integration.refresh_status}, "
            f"error={getattr(integration, 'refresh_error', 'unknown')}"
        )
    return integration_id


@pytest.fixture(scope="session")
def syntara_admin_user(syntara_api: SyntaraApiRegistry) -> UserInfo:
    """Get admin user ID."""
    return cast("UserInfo", syntara_api.authentication.get_current_user().assert_and_get())


# ---------------------------------------------------------------------------
# Workflow fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workflow_factory(
    syntara_api: SyntaraApiRegistry,
) -> Generator[Callable[[WorkflowCreate], WorkflowRead], None, None]:
    """Factory that creates workflows with automatic cleanup."""
    created_workflow_ids: list[UUID] = []

    def _create(workflow_data: WorkflowCreate) -> WorkflowRead:
        workflow: WorkflowRead = syntara_api.workflows.create(body=workflow_data).assert_and_get()
        created_workflow_ids.append(workflow.id)
        return workflow

    yield _create

    for workflow_id in created_workflow_ids:
        try:
            syntara_api.workflows.delete(workflow_id=workflow_id)
        except Exception:
            pass  # Best effort cleanup


@pytest.fixture
def cleanup_workflows(syntara_api: SyntaraApiRegistry) -> Generator[list[UUID], None, None]:
    """List to register workflow IDs for cleanup after test.

    Use when tests need to call syntara_api.workflows.create() directly
    (e.g., to validate response status codes) instead of using workflow_factory.

    Usage:
        def test_create_workflow(syntara_api, cleanup_workflows):
            response = syntara_api.workflows.create(...)
            if response.status_code == 201:
                cleanup_workflows.append(response.parsed.id)
            assert response.status_code == 201
    """
    workflow_ids: list[UUID] = []
    yield workflow_ids

    for workflow_id in workflow_ids:
        try:
            syntara_api.workflows.delete(workflow_id=workflow_id)
        except Exception:
            pass  # Best effort cleanup


# ---------------------------------------------------------------------------
# LLM / credential fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def llm_model() -> str:
    """Return the LLM model to use in agentic node configs.

    Reads APP_OPENROUTER_MODEL from the environment; falls back to the
    app's default so local runs work without any extra configuration.
    """
    return os.environ.get("APP_OPENROUTER_MODEL", "anthropic/claude-sonnet-4")


@pytest.fixture(scope="session")
def llm_credential_id(
    syntara_api: SyntaraApiRegistry, worker_id: str, first_project_id: UUID
) -> Generator[str, None, None]:
    """Create an LLM Provider credential for e2e tests and yield its UUID.

    Reads APP_OPENROUTER_API_KEY from the environment; skips if not set.
    The credential is deleted on teardown.
    """
    api_key = os.environ.get("APP_OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("APP_OPENROUTER_API_KEY not set — LLM credential required")

    types_list = syntara_api.credentials.list_types().assert_and_get()
    llm_type_id: UUID | None = None
    for ct in types_list.resources:
        if "llm" in ct.name.lower():
            llm_type_id = UUID(str(ct.id))
            break
    assert llm_type_id is not None, "LLM Provider credential type not found — is the database seeded?"

    cred_name = f"e2e-llm-credential-{worker_id}"
    cred = syntara_api.credentials.create(
        body=CredentialCreate(
            name=cred_name,
            credential_type_id=llm_type_id,
            project_id=first_project_id,
            inputs=CredentialCreateInputs.from_dict(
                {
                    "api_key": api_key,
                }
            ),
        ),
    ).assert_and_get()
    cred_id = str(cred.id)

    yield cred_id

    try:
        syntara_api.credentials.delete(credential_id=UUID(cred_id))
    except Exception:
        pass


@pytest.fixture(scope="session")
def llm_model_id(
    syntara_api: SyntaraApiRegistry, llm_credential_id: str, llm_model: str, worker_id: str
) -> Generator[str, None, None]:
    """Create an LLM provider integration with a model and yield the LLMModel UUID.

    Creates a CUSTOM LLM provider integration pointing at the OpenRouter API,
    seeds it with the model from APP_OPENROUTER_MODEL, and yields the database
    UUID of that LLMModel record.  The integration (and its models) are deleted
    on teardown.
    """
    integration = syntara_api.integrations.create(
        body=IntegrationCreate(
            name=f"e2e-llm-provider-{worker_id}",
            description="LLM provider for E2E tests",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration=LLMProviderConfiguration(
                provider_hint=LLMProviderHint.CUSTOM,
                base_url="https://openrouter.ai/api/v1",
            ),
            management_credential_id=UUID(llm_credential_id),
            discovered_models=[
                InitialModelSelection(
                    model_id=llm_model,
                    name=llm_model,
                    enabled=True,
                    is_default=True,
                ),
            ],
        ),
    ).assert_and_get()
    integration_id = integration.id

    models_resp = syntara_api.integrations.list_models(integration_id=integration_id)
    models = models_resp.assert_and_get()
    assert models.resources, "LLM provider integration has no models after creation"
    model_uuid = str(models.resources[0].id)

    yield model_uuid

    try:
        syntara_api.integrations.delete(integration_id=integration_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Project fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def first_project_id(syntara_api: SyntaraApiRegistry) -> UUID:
    """Return the first available non-builtin project ID.

    Tests that need a valid project ID can use this fixture.
    Skips built-in projects since workflow creation is blocked in them.
    """
    return get_first_non_builtin_project_id(syntara_api)


# ---------------------------------------------------------------------------
# User / resource factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def local_user_factory(
    syntara_api: SyntaraApiRegistry,
) -> Generator[Callable[..., tuple[UserRead, str]], None, None]:
    """Factory that creates a local user and cleans up after the test.

    Returns a tuple of (UserRead, password) so tests can verify login behavior.
    Accepts optional overrides for username, email, first/last name, and password.
    """
    created_user_ids: list[UUID] = []

    def _create(
        *,
        username: str | None = None,
        email: str | None | Unset = UNSET,
        first_name: str = "Test",
        last_name: str = "Local User",
        password: str | None = None,
    ) -> tuple[UserRead, str]:
        username = username or unique_name("e2e-test-user")
        password = password or generate_test_password()
        if isinstance(email, Unset):
            email = f"{username}@example.com"

        resp = syntara_api.users.create(
            body=UserCreate(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                is_enabled=True,
            )
        )
        assert resp.status_code == 201
        user = resp.assert_and_get()
        created_user_ids.append(user.id)
        return user, password

    yield _create

    for user_id in created_user_ids:
        try:
            syntara_api.users.delete(user_id=user_id)
        except Exception:
            logger.warning("Failed to clean up local user %s", user_id, exc_info=True)


@pytest.fixture
def integration_factory(
    syntara_api: SyntaraApiRegistry,
) -> Generator[Callable[[IntegrationCreate], dict[str, Any]], None, None]:
    """Factory that creates integrations with automatic cleanup.

    Creates integrations (MCP servers, LLM providers, AAP gateways) and tracks
    them for automatic cleanup on test teardown.

    Usage:
        def test_something(integration_factory):
            integration = integration_factory(
                IntegrationCreate(
                    name="test-mcp",
                    integration_type=IntegrationType.MCP_SERVER,
                    configuration=MCPServerConfiguration(...),
                )
            )
            # Use integration["id"]
            # Cleanup happens automatically

    Args:
        syntara_api: Admin API client for creating integrations

    Returns:
        Factory function that creates and tracks integrations

    """
    created_ids: list[UUID] = []

    def _create(body: IntegrationCreate) -> dict[str, Any]:
        integration = syntara_api.integrations.create(body=body).assert_and_get()
        created_ids.append(integration.id)
        result: dict[str, Any] = integration.to_dict()
        return result

    yield _create

    for integration_id in created_ids:
        try:
            syntara_api.integrations.delete(integration_id=integration_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator_authenticated_cli(syntara_base_url: str) -> Callable[[list[str]], Result]:
    """Invokable orchestrator cli with base url and a fresh admin token."""
    from orchestrator_cli import app  # lazy import — optional dependency

    runner = CliRunner()
    token = _generate_e2e_token(syntara_base_url)

    def invoke(args: list[str]) -> Result:
        return runner.invoke(
            app,
            [
                "--base-url",
                syntara_base_url,
                "--token",
                token,
                *args,
            ],
        )

    return invoke
