"""Pytest plugin entry point — registers E2E fixtures via pytest11 entry point.

App-level fixtures (database, client, temporal, etc.) that import from syntara.*
are registered via pytest_plugins in the repo's tests/conftest.py instead.
This keeps syntara.* out of the entry-point import chain, which runs before
pytest-cov can start its tracer.
"""

pytest_plugins = [
    "orchestrator_test_sdk.e2e.hooks",
    "orchestrator_test_sdk.e2e.factories",
    # Factory fixtures (create_workflow, create_user, etc.) — these only import
    # from syntara_api_client, not syntara.*, so they're safe in the entry point.
    "orchestrator_test_sdk.factories.credentials",
    "orchestrator_test_sdk.factories.groups",
    "orchestrator_test_sdk.factories.identity_providers",
    "orchestrator_test_sdk.factories.policies",
    "orchestrator_test_sdk.factories.projects",
    "orchestrator_test_sdk.factories.roles",
    "orchestrator_test_sdk.factories.users",
    "orchestrator_test_sdk.factories.workflows",
]
