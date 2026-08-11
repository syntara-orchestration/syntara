"""App-level test infrastructure: env setup and live fixtures.

SDK fixtures (e2e + performance — require a live deployment):
  - live.py        nexus_base_url, nexus_client, syntara_api, auth_headers

Pytest hooks (global infrastructure for all test types):
  - _hooks.py      worker_id, --run-performance flag, collection filtering, cleanup

Support utilities (no pytest fixtures — importable from any test context):
  - mock_mcp_provider    MockMCPProvider class
  - mcp_servers          ExampleMCPServer, ForbiddenMCPServer
  - mock_shared_resources  mock SQLModel table implementations
  - files                generate_large_file, get_fixtures_dir

Shared fixtures (unit + integration) live in tests/fixtures/:
  - database.py    test_db_engine, test_db_session, test_session_factory
  - users.py       default_user_data, user_factory, test_user, admin_user
  - tools.py       test_tool
  - mocks.py       mock_session_factory, mock_token_calculator, mock_compressor
  - factories.py   executions_factory
  - settings.py    override_settings, override_runtime_settings, fast_retry_settings,
                   FakeSettingsCache

Unit-specific fixtures live in tests/unit/fixtures/:
  - jwt.py         token_service
  - mocks.py       mock_websocket
  - settings.py    fast_workflow_client_settings
  - tools.py       test_provider_factory, test_tool_service

Integration-specific fixtures live in tests/integration/fixtures/:
  - client.py      session_app, base_client, auth_client, sync_test_client
  - groups.py      test_group, group_with_members, multiple_test_groups
  - temporal.py    temporal_env, temporal_worker, task_queue
  - workflows.py   test_workflow, test_execution, test_activity
  - database.py    test_db_admin_url, test_cache
  - factories.py   workflow_factory, credential_factory, activities_factory, etc.
  - jwt.py         jwt_client, create_jwt_for_user
  - mocks.py       mock_openrouter_llm
  - settings.py    disabled_retry_settings
  - tools.py       test_mcp_integration, tool_factory
  - users.py       non_local_user, auth_client_as_admin, multiple_local_users
"""

# Prevent local .env from leaking into tests. Must be set before Settings is
# imported, since _get_env_file() is evaluated at class-definition time.
import os as _os

_os.environ.setdefault("APP_ENV_FILE_PATH", "/dev/null")
_os.environ.setdefault(
    "APP_SECRET_ENCRYPTION_KEY",
    "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
)
