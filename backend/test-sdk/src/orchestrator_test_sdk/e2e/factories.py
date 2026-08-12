"""Reusable factory helpers and pytest fixtures for E2E resource creation.

Provides three layers:

1. **Plain helper functions** — ``create_user``, ``create_project``, etc.
   Callable from any pytest scope; no automatic cleanup.

2. **ResourceTracker** — a plain class that wraps the helpers and tracks
   created IDs for batch cleanup.  Designed for module-scoped fixtures
   that cannot depend on function-scoped factory fixtures.

3. **Pytest factory fixtures** — function-scoped fixtures that yield a
   callable and clean up on teardown.
"""

from __future__ import annotations

import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from syntara_api_client.api import SyntaraApiRegistry

from orchestrator_test_sdk.e2e.auth import _login, _make_client, admin_password
from orchestrator_test_sdk.e2e.helpers import get_first_non_builtin_project_id

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from uuid import UUID

    from syntara_api_client.models.integration_create import IntegrationCreate
    from syntara_api_client.models.workflow_create import WorkflowCreate
    from syntara_api_client.models.workflow_read import WorkflowRead

# ---------------------------------------------------------------------------
# Module-scoped admin fixture (fresh token per module — avoids 15-min expiry)
# ---------------------------------------------------------------------------

_ADMIN_TOKEN_READY_TIMEOUT = 20.0


@pytest.fixture(scope="module")
def admin_api(nexus_base_url: str) -> SyntaraApiRegistry:
    """Admin API registry with a fresh JWT per test module.

    Retries login until the issued token is accepted by the API. This guards
    against the global-revocation TTL window that test_global_revocation.py
    leaves behind — tokens issued within that window are rejected even though
    login returns 200, until the cache expires (~10 s).
    """
    password = admin_password()
    deadline = time.monotonic() + _ADMIN_TOKEN_READY_TIMEOUT

    last_exc: Exception | None = None
    last_status: int | None = None
    while True:
        try:
            token = _login(nexus_base_url, "admin", password)
            client = _make_client(nexus_base_url, token)
            api = SyntaraApiRegistry(client)
            resp = api.settings.list(limit=1)
            if resp.status_code == HTTPStatus.OK:
                return api
            last_status = resp.status_code
        except Exception as exc:
            last_exc = exc
        if time.monotonic() >= deadline:
            if last_exc:
                detail = f" (last error: {last_exc})"
            elif last_status:
                detail = f" (last HTTP status: {last_status})"
            else:
                detail = ""
            pytest.fail(f"admin_api: API did not accept a fresh token within {_ADMIN_TOKEN_READY_TIMEOUT:.0f}s{detail}")
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Project, integration, and workflow fixtures (API-level, for E2E tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def first_project_id(syntara_api: SyntaraApiRegistry) -> UUID:
    """Return the first available non-builtin project ID.

    Tests that need a valid project ID can use this fixture.
    Skips built-in projects since workflow creation is blocked in them.
    """
    return get_first_non_builtin_project_id(syntara_api)


@pytest.fixture
def integration_factory(
    syntara_api: SyntaraApiRegistry,
) -> Generator[Callable[[IntegrationCreate], dict[str, Any]], None, None]:
    """Factory that creates integrations via the API with automatic cleanup."""
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


@pytest.fixture
def workflow_factory(
    syntara_api: SyntaraApiRegistry,
) -> Generator[Callable[[WorkflowCreate], WorkflowRead], None, None]:
    """Factory that creates workflows via the API with automatic cleanup."""
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
            pass
