"""Shared pytest fixtures for all backend tests.

App-level fixtures are loaded here (not via the pytest11 entry point) so that
syntara.* imports happen AFTER pytest-cov starts its coverage tracer.
"""

pytest_plugins = [
    # MUST stay first: preloads regopy's native library before the fixture
    # plugins below pull in SQLAlchemy/greenlet — otherwise every in-process
    # rego evaluation in this pytest run leaks ~69 KB natively — and guards
    # the resulting import order for the whole session.
    # See docs/standards/imports-and-modules.md ("Native import order").
    "tests.fixtures.regopy_preload",
    # Logging setup, performance marker, worker_id fixture, and cleanup hooks
    "tests.fixtures.hooks",
    # Dynamic xfail from remote URL (enabled via --xfail-from-url)
    "tests.fixtures.xfail_from_url",
    # Shared fixtures used across unit, integration, performance, and E2E tests
    "tests.fixtures.database",
    "tests.fixtures.users",
    "tests.fixtures.tools",
    "tests.fixtures.mocks",
    "tests.fixtures.settings",
    "tests.fixtures.factories",
    # Cross-layer fixtures: used by shared factories (tests.fixtures.factories)
    # which are consumed by both unit and integration tests.
    "tests.integration.fixtures.workflows",
    "tests.integration.fixtures.tools",
    # Live-deployment fixtures (syntara_base_url, syntara_api, ...) for performance/e2e tests.
    "orchestrator_test_sdk.app.live",
]
