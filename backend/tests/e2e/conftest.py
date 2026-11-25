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

pytest_plugins = [
    "orchestrator_test_sdk.app.live",
    "orchestrator_test_sdk.e2e.fixtures",
]
