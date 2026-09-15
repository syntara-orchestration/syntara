"""E2E-level fixtures for backend E2E tests.

Loads orchestrator_test_sdk.e2e.fixtures which provides:
- autouse fixtures: reset_async_client, _wait_for_api
- session fixtures: syntara_client (with _AutoRefreshAuth), syntara_api, viewer_*, auditor_*
- factory fixtures: integration_factory, workflow_factory, cleanup_workflows, local_user_factory
- helper fixtures: first_project_id, mcp_integration_id, syntara_api_admin_group_id, etc.

These override the API-level stubs from orchestrator_test_sdk.e2e.factories (which
is registered globally in the plugin) for the backend/tests/e2e/ subtree, and
also override the DB-level factories from orchestrator_test_sdk.app.factories
(loaded by backend/tests/conftest.py) for this subtree.
"""

import pytest
from orchestrator_test_sdk.e2e.helpers import HTTPBIN_URL, httpbin_available

pytest_plugins = [
    "orchestrator_test_sdk.app.live",
    "orchestrator_test_sdk.e2e.fixtures",
]


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip requires_httpbin tests at runtime if httpbin is not reachable.

    The @requires_httpbin mark is a plain mark (not a collection-time skipif)
    so that tests are not inadvertently collected when httpbin is up at import
    time but goes down before the test body executes.  This hook performs a
    fresh network check immediately before each marked test runs.
    """
    if item.get_closest_marker("requires_httpbin") and not httpbin_available():
        pytest.skip(f"httpbin not reachable at {HTTPBIN_URL}. Set HTTPBIN_URL to override.")
