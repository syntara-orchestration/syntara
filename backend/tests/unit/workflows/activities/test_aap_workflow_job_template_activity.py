"""Unit tests for AAP workflow job template activity (T006).

Tests AAP workflow job template execution including:
- Basic workflow execution (success/failure)
- Heartbeat during polling
- Cancellation handling
- Expression resolution
- Authentication (token and basic)
- Timeout handling
- Error handling
"""

from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine import constants
from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import (
    execute_aap_workflow_job_template_activity,
)
from syntara.workflows.workflow_engine.models import AAPWorkflowJobTemplateExecutorParameters

# Test constants
TEST_AAP_URL = "http://test.aap"
TEST_TOKEN = "test_token"  # noqa: S105
TEST_TOKEN_123 = "test_token_123"  # noqa: S105
TEST_USERNAME = "admin"
TEST_PASSWORD = "secret123"  # noqa: S105


def build_config(**kwargs: object) -> AAPWorkflowJobTemplateExecutorParameters:
    """Helper to build configs using snake_case keys while keeping mypy happy."""
    return AAPWorkflowJobTemplateExecutorParameters.model_validate(kwargs)


_DEFAULT_RESOLVED_INTEGRATION: dict[str, object] = {
    "base_url": "https://aap.example.com",
    "verify_ssl": True,
}


def build_activity_config(**kwargs: object) -> dict[str, object]:
    """Helper to build flat activity config dict (v2 convention)."""
    config = build_config(**kwargs)
    result = config.model_dump(by_alias=True)
    result["_resolved_integration"] = _DEFAULT_RESOLVED_INTEGRATION
    return result


def create_http_response(
    status_code: int, json: dict[str, object] | None = None, text: str | None = None
) -> httpx.Response:
    """Helper to create mock HTTP responses."""
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", TEST_AAP_URL),
        json=json,
        text=text,
    )


def create_workflow_workflow_job_status_response(
    workflow_job_id: int = 123,
    status: str = "successful",
    **overrides: object,
) -> httpx.Response:
    """Create a mock AAP workflow job status response with sensible defaults.

    All fields can be overridden via keyword arguments.
    """
    data: dict[str, object] = {
        "id": workflow_job_id,
        "status": status,
        "artifacts": {},
        "created": "2026-04-23T20:10:58Z",
        "started": "2026-04-23T20:11:00Z",
        "finished": "2026-04-23T20:11:10Z",
        **overrides,
    }
    return create_http_response(200, data)


def create_successful_workflow_job_mocks(
    workflow_job_id: int = 123,
) -> dict[str, httpx.Response]:
    """Create standard mock responses for successful AAP workflow job execution.

    Args:
        workflow_job_id: Workflow job ID to use in responses

    Returns:
        Dictionary with 'launch' and 'status' response mocks

    """
    return {
        "launch": create_http_response(
            200, {"id": workflow_job_id, "url": f"/api/v2/workflow_jobs/{workflow_job_id}/"}
        ),
        "status": create_workflow_workflow_job_status_response(workflow_job_id=workflow_job_id),
    }


def build_aap_settings_overrides(
    base_url: str = "https://aap.example.com",
    token: str | None = TEST_TOKEN,
    username: str | None = None,
    password: str | None = None,
    poll_interval: float = 0.01,
    timeout: int = 30,
) -> dict[str, object]:
    """Helper to build AAP settings overrides."""
    overrides: dict[str, object] = {
        "aap_base_url": base_url,
        "aap_poll_interval_seconds": poll_interval,
        "aap_timeout_seconds": timeout,
    }

    if token:
        overrides["aap_token"] = SecretStr(token)
        overrides["aap_username"] = None
        overrides["aap_password"] = None
    else:
        overrides["aap_token"] = None
        overrides["aap_username"] = username
        overrides["aap_password"] = SecretStr(password) if password else None

    return overrides


@pytest.fixture
def aap_settings_overrides() -> dict[str, object]:
    """Default AAP settings overrides for tests."""
    return build_aap_settings_overrides()


@pytest.fixture
def mock_activity_context(
    override_settings: Callable[..., AbstractContextManager[object]],
    aap_settings_overrides: dict[str, object],
) -> Generator[None, None, None]:
    """Mock common activity context (settings, is_cancelled, heartbeat)."""
    with (
        override_settings(**aap_settings_overrides),
        patch("temporalio.activity.is_cancelled", return_value=False),
        patch("temporalio.activity.heartbeat"),
    ):
        yield


class TestAAPWorkflowJobTemplateExecution:
    """Test AAP workflow job template execution (basic flow)."""

    @pytest.mark.asyncio
    async def test_successful_workflow_execution(self, mock_activity_context: object) -> None:
        """Test successful workflow template launch and completion."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        status_response = create_workflow_workflow_job_status_response(
            workflow_job_id=123, artifacts={"changed": 5, "ok": 10, "failed": 0}
        )

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=status_response),
        ):
            activity_config = build_activity_config(
                workflow_job_template_id=42,
                inventory=123,
                extra_vars={"version": "1.0.0"},
            )

            result = await execute_aap_workflow_job_template_activity(activity_config, None)

            assert result["output"]["workflow_job_id"] == 123
            assert result["output"]["workflow_job_status"] == "successful"
            assert result["output"]["artifacts"]["changed"] == 5
            assert result["output"]["created"] == "2026-04-23T20:10:58Z"
            assert result["output"]["started"] == "2026-04-23T20:11:00Z"
            assert result["output"]["finished"] == "2026-04-23T20:11:10Z"

    @pytest.mark.asyncio
    async def test_failed_workflow_execution(self, mock_activity_context: object) -> None:
        """Test workflow template execution failure returns error result."""
        launch_response = create_http_response(200, {"id": 456, "url": "/api/v2/workflow_jobs/456/"})
        failed_status_response = create_workflow_workflow_job_status_response(workflow_job_id=456, status="failed")

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=failed_status_response),
        ):
            activity_config = build_activity_config(workflow_job_template_id=99)

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_workflow_job_template_activity(activity_config, None)
            assert exc_info.value.type == "AAPWorkflowJobExecutionError"
            assert "456" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_canceled_workflow_job_raises_application_error(self, mock_activity_context: object) -> None:
        """Test canceled workflow job raises ApplicationError with correct type."""
        launch_response = create_http_response(200, {"id": 456, "url": "/api/v2/workflow_jobs/456/"})
        canceled_status_response = create_workflow_workflow_job_status_response(workflow_job_id=456, status="canceled")

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=canceled_status_response),
        ):
            activity_config = build_activity_config(workflow_job_template_id=99)

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_workflow_job_template_activity(activity_config, None)
            assert exc_info.value.type == "AAPWorkflowJobExecutionError"
            assert "456" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extra_vars_forwarded_to_aap(self, mock_activity_context: object) -> None:
        """Test extra_vars are forwarded correctly to AAP API.

        In V2, template expressions are resolved by the workflow engine before
        calling the activity. The activity receives already-resolved values.
        """
        launch_response = create_http_response(200, {"id": 789, "url": "/api/v2/workflow_jobs/789/"})

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_workflow_workflow_job_status_response(workflow_job_id=789),
            ),
        ):
            # V2: templates are resolved by dispatcher before reaching the activity
            activity_config = build_activity_config(
                workflow_job_template_id=42,
                extra_vars={
                    "app_version": "2.0.0",
                    "deploy_env": "staging",
                },
            )

            await execute_aap_workflow_job_template_activity(activity_config, None)

            # Verify extra_vars were resolved and sent with correct snake_case key
            call_body = mock_post.call_args.kwargs["json"]
            assert call_body["extra_vars"]["app_version"] == "2.0.0"
            assert call_body["extra_vars"]["deploy_env"] == "staging"

    @pytest.mark.asyncio
    async def test_nested_extra_vars_forwarded_to_aap(self, mock_activity_context: object) -> None:
        """Test nested lists and dictionaries within extra_vars are forwarded correctly.

        In V2, template expressions are resolved by the workflow engine before
        calling the activity. The activity receives already-resolved values.
        """
        launch_response = create_http_response(200, {"id": 890, "url": "/api/v2/workflow_jobs/890/"})

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_workflow_workflow_job_status_response(workflow_job_id=890),
            ),
        ):
            # V2: templates are resolved by dispatcher before reaching the activity
            activity_config = build_activity_config(
                workflow_job_template_id=42,
                extra_vars={
                    "hosts": [
                        {"name": "server1", "ip": "10.0.0.1", "port": 8080},
                        {"name": "server2", "ip": "10.0.0.2", "port": 8081},
                    ],
                    "parameters": {"timeout": 30, "retries": 3},
                },
            )

            await execute_aap_workflow_job_template_activity(activity_config, None)

            # Verify nested structures were resolved correctly
            call_body = mock_post.call_args.kwargs["json"]
            assert call_body["extra_vars"]["hosts"][0]["ip"] == "10.0.0.1"
            assert call_body["extra_vars"]["hosts"][0]["port"] == 8080
            assert call_body["extra_vars"]["hosts"][1]["ip"] == "10.0.0.2"
            assert call_body["extra_vars"]["hosts"][1]["port"] == 8081
            assert call_body["extra_vars"]["parameters"]["timeout"] == 30
            assert call_body["extra_vars"]["parameters"]["retries"] == 3


class TestAAPWorkflowJobTemplateHeartbeat:
    """Test heartbeat functionality for long-running workflows."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    async def test_heartbeat_sent_during_polling(
        self,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test activity sends heartbeats during polling loop."""
        # Mock responses - multiple polling iterations (running → running → successful)
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        running_response_1 = create_http_response(200, {"id": 123, "status": "running"})
        running_response_2 = create_http_response(200, {"id": 123, "status": "running"})

        mock_heartbeat = MagicMock()

        with (
            override_settings(**aap_settings_overrides),
            patch("temporalio.activity.heartbeat", mock_heartbeat),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            # Poll sequence: running, running, successful
            mock_get.side_effect = [
                running_response_1,
                running_response_2,
                create_workflow_workflow_job_status_response(),
            ]

            activity_config = build_activity_config(workflow_job_template_id=42)

            await execute_aap_workflow_job_template_activity(activity_config, None)

            # Verify heartbeats were sent (at least 2 times during polling)
            assert mock_heartbeat.call_count >= 2

            # Verify heartbeat payload contains workflow_job_id
            for call_obj in mock_heartbeat.call_args_list:
                payload = call_obj[0][0]
                assert payload["partial_output"]["workflow_job_id"] == 123


class TestAAPWorkflowJobTemplateCancellation:
    """Test cancellation handling."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.heartbeat")
    async def test_cancel_aap_workflow_when_activity_cancelled(
        self,
        mock_heartbeat: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test AAP workflow is cancelled when activity is cancelled."""
        from temporalio.exceptions import CancelledError

        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        running_response = create_http_response(200, {"id": 123, "status": "running"})
        cancel_response = create_http_response(200, {})

        # Mock activity.is_cancelled to return True after first poll
        mock_is_cancelled = MagicMock(side_effect=[False, True])

        with (
            override_settings(**aap_settings_overrides),
            patch("temporalio.activity.is_cancelled", mock_is_cancelled),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=running_response),
        ):
            # Launch returns success, cancel returns success
            mock_post.side_effect = [launch_response, cancel_response]

            activity_config = build_activity_config(workflow_job_template_id=42)

            # Should raise CancelledError
            with pytest.raises(CancelledError):
                await execute_aap_workflow_job_template_activity(activity_config, None)

            # Verify cancel endpoint was called
            cancel_call = mock_post.call_args_list[1]
            assert "/workflow_jobs/123/cancel/" in str(cancel_call)


class TestAAPWorkflowJobTemplateErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_launch_failure_authentication_error(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test workflow launch fails with authentication error."""
        with (
            override_settings(**aap_settings_overrides),
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "401 Unauthorized",
                    request=MagicMock(),
                    response=create_http_response(401, text="Authentication failed"),
                ),
            ),
        ):
            activity_config = build_activity_config(workflow_job_template_id=42)

            with pytest.raises(ApplicationError, match="Failed to launch"):
                await execute_aap_workflow_job_template_activity(activity_config, None)

    @pytest.mark.asyncio
    async def test_launch_failure_template_not_found(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test workflow launch fails with 404 template not found."""
        with (
            override_settings(**aap_settings_overrides),
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "404 Not Found",
                    request=MagicMock(),
                    response=create_http_response(404, text="Template not found"),
                ),
            ),
        ):
            activity_config = build_activity_config(workflow_job_template_id=999)

            with pytest.raises(ApplicationError, match="Failed to launch"):
                await execute_aap_workflow_job_template_activity(activity_config, None)

    @pytest.mark.asyncio
    async def test_network_connection_error(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test network connection failure."""
        with (
            override_settings(**aap_settings_overrides),
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("Connection refused"),
            ),
        ):
            activity_config = build_activity_config(workflow_job_template_id=42)

            with pytest.raises(ApplicationError, match="Failed to connect to AAP"):
                await execute_aap_workflow_job_template_activity(activity_config, None)

    @pytest.mark.asyncio
    async def test_invalid_config_missing_workflow_job_template_id(self) -> None:
        """Test error with missing workflow_job_template_id raises ApplicationError."""
        activity_config: dict[str, object] = {}  # Missing workflow_job_template_id

        with pytest.raises(ApplicationError) as exc_info:
            await execute_aap_workflow_job_template_activity(activity_config, None)
        assert exc_info.value.type == "ConfigError"


class TestAAPWorkflowJobTemplateTimeout:
    """Test timeout handling for long-running workflows."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_workflow_timeout_during_polling(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        override_runtime_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test workflow execution timeout is enforced during polling."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        running_response = create_http_response(200, {"id": 123, "status": "running"})

        # Mock time.time() to simulate timeout after 3 polls
        # Use a callable to avoid StopIteration
        start_time = 1000.0
        time_values = [start_time, start_time + 1, start_time + 2, start_time + 11]
        time_counter = {"index": 0}

        def mock_time() -> float:
            idx = time_counter["index"]
            # After exhausting predefined values, keep returning a time that exceeds timeout
            if idx >= len(time_values):
                return start_time + 20  # Well beyond timeout
            value = time_values[idx]
            time_counter["index"] += 1
            return value

        with (
            override_settings(**aap_settings_overrides),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=running_response),
            patch("time.time", side_effect=mock_time),
        ):
            activity_config = build_activity_config(workflow_job_template_id=42)
            activity_config[constants.ENGINE_TIMEOUT_SECONDS_KEY] = 10

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_workflow_job_template_activity(activity_config, None)
            assert "timed out after 10 seconds" in str(exc_info.value)
            assert "123" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_workflow_completes_within_timeout(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test workflow completes successfully when it finishes before timeout."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        running_response = create_http_response(200, {"id": 123, "status": "running"})

        # Mock time to show workflow completes within timeout
        # Use a callable that increments time to avoid StopIteration
        start_time = 1000.0
        time_counter = {"value": start_time}

        def mock_time() -> float:
            current = time_counter["value"]
            time_counter["value"] += 1.0  # Increment by 1 second each call
            return current

        with (
            override_settings(**aap_settings_overrides),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("time.time", side_effect=mock_time),
        ):
            # Poll sequence: running, successful
            mock_get.side_effect = [running_response, create_workflow_workflow_job_status_response()]

            # Configure timeout of 10 seconds (workflow completes in ~2 seconds)
            activity_config = build_activity_config(workflow_job_template_id=42, timeout=10)

            result = await execute_aap_workflow_job_template_activity(activity_config, None)

            # Workflow should complete successfully
            assert result["output"]["workflow_job_status"] == "successful"
            assert result["output"]["workflow_job_id"] == 123


class TestAAPWorkflowJobTemplateAuthentication:
    """Test authentication handling."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.heartbeat")
    @patch("temporalio.activity.is_cancelled", return_value=False)
    async def test_token_authentication(
        self,
        mock_is_cancelled: object,
        mock_heartbeat: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test AAP token authentication is used."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})

        with (
            override_settings(**build_aap_settings_overrides(token=TEST_TOKEN_123)),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_workflow_workflow_job_status_response(),
            ),
        ):
            activity_config = build_activity_config(workflow_job_template_id=42)

            await execute_aap_workflow_job_template_activity(activity_config, None)

            # Verify Authorization header with Bearer token
            assert "headers" in mock_post.call_args.kwargs
            assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer test_token_123"

    @pytest.mark.asyncio
    @patch("temporalio.activity.heartbeat")
    @patch("temporalio.activity.is_cancelled", return_value=False)
    async def test_basic_authentication(
        self,
        mock_is_cancelled: object,
        mock_heartbeat: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test AAP basic authentication is used."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})

        with (
            override_settings(
                **build_aap_settings_overrides(token=None, username=TEST_USERNAME, password=TEST_PASSWORD)
            ),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_workflow_workflow_job_status_response(),
            ),
        ):
            activity_config = build_activity_config(workflow_job_template_id=42)

            await execute_aap_workflow_job_template_activity(activity_config, None)

            # Verify BasicAuth was used
            assert "auth" in mock_post.call_args.kwargs
            assert isinstance(mock_post.call_args.kwargs["auth"], httpx.BasicAuth)

    @pytest.mark.asyncio
    async def test_aap_activity_with_pre_resolved_parameters(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test AAP activity receives pre-resolved config (v2: dispatcher resolves templates)."""
        launch_response = create_http_response(201, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("temporalio.activity.is_cancelled", return_value=False),
            patch("temporalio.activity.heartbeat"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_workflow_workflow_job_status_response(),
            ),
        ):
            # V2: flat config with already-resolved values
            activity_config = build_activity_config(workflow_job_template_id=42, limit="host1")

            await execute_aap_workflow_job_template_activity(activity_config, None)

            # Verify resolved values were used
            post_body = mock_post.call_args.kwargs["json"]
            assert post_body["limit"] == "host1"


class TestAAPWorkflowJobTemplateNameBasedReference:
    """Test name-based workflow template references."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_successful_name_based_execution(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test successful workflow execution using name-based reference."""
        mocks = create_successful_workflow_job_mocks(workflow_job_id=123)

        # Mock lookup response
        lookup_response = create_http_response(200, {"count": 1, "results": [{"id": 42, "name": "Deploy Workflow"}]})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            # GET calls: lookup, status
            mock_get.side_effect = [lookup_response, mocks["status"]]

            activity_config = build_activity_config(
                workflow_job_template_name="Deploy Workflow",
                organization_name="Default",
                extra_vars={"version": "1.0.0"},
            )

            result = await execute_aap_workflow_job_template_activity(activity_config, None)

            assert result["output"]["workflow_job_id"] == 123
            assert result["output"]["workflow_job_status"] == "successful"

            # Verify lookup was called with correct params
            lookup_call = mock_get.call_args_list[0]
            assert "workflow_job_templates" in str(lookup_call.args[0])
            assert lookup_call.kwargs["params"]["name"] == "Deploy Workflow"
            assert lookup_call.kwargs["params"]["organization__name"] == "Default"

            # Verify POST was called with numeric ID (not named URL)
            post_url = mock_post.call_args.args[0]
            assert "/workflow_job_templates/42/launch/" in post_url

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_lookup_template_not_found(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test error when template lookup returns no results."""
        # Mock lookup response with no results
        lookup_response = create_http_response(200, {"count": 0, "results": []})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=lookup_response),
        ):
            activity_config = build_activity_config(
                workflow_job_template_name="Nonexistent Template",
                organization_name="Default",
            )

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_workflow_job_template_activity(activity_config, None)
            assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_lookup_multiple_templates_found(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test error when template lookup returns multiple results."""
        # Mock lookup response with multiple results
        lookup_response = create_http_response(
            200,
            {
                "count": 2,
                "results": [
                    {"id": 42, "name": "Deploy Workflow"},
                    {"id": 43, "name": "Deploy Workflow"},
                ],
            },
        )

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=lookup_response),
        ):
            activity_config = build_activity_config(
                workflow_job_template_name="Deploy Workflow",
                organization_name="Default",
            )

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_workflow_job_template_activity(activity_config, None)
            assert "Multiple workflow job templates" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("config_kwargs", "should_pass", "error_match"),
        [
            # Valid cases - should pass
            ({"workflow_job_template_id": 42}, True, None),
            ({"workflow_job_template_name": "Deploy", "organization_name": "Default"}, True, None),
            ({"workflow_job_template_name": "  Deploy  ", "organization_name": "  Default  "}, True, None),
            # Both ID and name is valid - ID takes precedence
            (
                {
                    "workflow_job_template_id": 42,
                    "workflow_job_template_name": "Deploy",
                    "organization_name": "Default",
                },
                True,
                None,
            ),
            # Invalid cases - should raise ValidationError
            (
                {"workflow_job_template_name": "Deploy"},
                False,
                "organization_name is required when using workflow_job_template_name",
            ),
            ({"organization_name": "Default"}, False, "workflow_job_template_id or workflow_job_template_name"),
            ({"extra_vars": {"foo": "bar"}}, False, "workflow_job_template_id or workflow_job_template_name"),
            (
                {"workflow_job_template_name": "", "organization_name": "Default"},
                False,
                "workflow_job_template_id or workflow_job_template_name",
            ),
            (
                {"workflow_job_template_name": "Deploy", "organization_name": ""},
                False,
                "organization_name is required when using workflow_job_template_name",
            ),
        ],
        ids=[
            "valid_id_only",
            "valid_name_and_org",
            "valid_name_and_org_with_whitespace",
            "valid_both_id_and_name",
            "invalid_name_without_org",
            "invalid_org_without_name",
            "invalid_neither_id_nor_name",
            "invalid_empty_template_name",
            "invalid_empty_organization_name",
        ],
    )
    def test_config_validation_mutual_exclusivity(
        self,
        config_kwargs: dict[str, Any],
        should_pass: bool,  # noqa: FBT001
        error_match: str | None,
    ) -> None:
        """Test config validation and whitespace stripping."""
        if should_pass:
            config = build_config(**config_kwargs)
            assert config is not None
            # Verify the expected field is set (and whitespace is stripped)
            if "workflow_job_template_id" in config_kwargs:
                assert config.workflow_job_template_id == config_kwargs["workflow_job_template_id"]
            if "workflow_job_template_name" in config_kwargs:
                assert config.workflow_job_template_name == config_kwargs["workflow_job_template_name"]
            if "organization_name" in config_kwargs:
                assert config.organization_name == config_kwargs["organization_name"]
        else:
            with pytest.raises(ValidationError, match=error_match):
                build_config(**config_kwargs)


class TestAAPInventoryNameBasedReference:
    """Test name-based inventory references."""

    @pytest.mark.parametrize(
        ("config_kwargs", "should_pass", "error_match"),
        [
            # Valid cases
            ({"workflow_job_template_id": 42, "inventory_id": 123}, True, None),
            ({"workflow_job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"}, True, None),
            ({"workflow_job_template_id": 42}, True, None),  # No inventory is optional
            # Both ID and name is valid - ID takes precedence
            (
                {
                    "workflow_job_template_id": 42,
                    "inventory_id": 123,
                    "inventory_name": "Prod",
                    "organization_name": "Default",
                },
                True,
                None,
            ),
            # Invalid cases
            (
                {"workflow_job_template_id": 42, "inventory_name": "Prod"},
                False,
                "organization_name is required when using inventory_name",
            ),
        ],
    )
    def test_inventory_config_validation(
        self,
        config_kwargs: dict[str, Any],
        should_pass: bool,  # noqa: FBT001
        error_match: str | None,
    ) -> None:
        """Test inventory config validation and requires org_name."""
        if should_pass:
            config = build_config(**config_kwargs)
            assert config is not None
        else:
            with pytest.raises(ValidationError, match=error_match):
                build_config(**config_kwargs)

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_inventory_name_lookup_and_workflow_execution(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test successful inventory lookup by name and workflow execution."""
        mocks = create_successful_workflow_job_mocks(workflow_job_id=456)
        inventory_lookup = create_http_response(200, {"count": 1, "results": [{"id": 789, "name": "Production"}]})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = [inventory_lookup, mocks["status"]]

            activity_config = build_activity_config(
                workflow_job_template_id=42,
                inventory_name="Production",
                organization_name="Default",
            )

            result = await execute_aap_workflow_job_template_activity(activity_config, None)

            assert result["output"]["workflow_job_id"] == 456
            assert result["output"]["workflow_job_status"] == "successful"
            # Verify inventory lookup
            assert "inventories" in str(mock_get.call_args_list[0].args[0])
            # Verify resolved inventory ID in POST body
            assert mock_post.call_args.kwargs["json"]["inventory"] == 789


class TestBuildLaunchBody:
    """Unit tests for _build_launch_body helper function."""

    def test_includes_inventory_when_provided(self) -> None:
        """Should include inventory ID in body when provided."""
        from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPWorkflowJobTemplateExecutorParameters

        config = AAPWorkflowJobTemplateExecutorParameters(workflow_job_template_id=1)
        body = _build_launch_body(config, inventory_id=42)

        assert body["inventory"] == 42

    def test_skips_inventory_when_none(self) -> None:
        """Should not include inventory in body when None."""
        from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPWorkflowJobTemplateExecutorParameters

        config = AAPWorkflowJobTemplateExecutorParameters(workflow_job_template_id=1)
        body = _build_launch_body(config, inventory_id=None)

        assert "inventory" not in body

    def test_skips_empty_extra_vars_dict(self) -> None:
        """Should not include extra_vars when empty dict."""
        from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPWorkflowJobTemplateExecutorParameters

        config = AAPWorkflowJobTemplateExecutorParameters(workflow_job_template_id=1, extra_vars={})
        body = _build_launch_body(config, inventory_id=None)

        assert "extra_vars" not in body

    def test_includes_non_empty_extra_vars_dict(self) -> None:
        """Should include extra_vars when non-empty dict."""
        from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPWorkflowJobTemplateExecutorParameters

        config = AAPWorkflowJobTemplateExecutorParameters(workflow_job_template_id=1, extra_vars={"key": "value"})
        body = _build_launch_body(config, inventory_id=None)

        assert body["extra_vars"] == {"key": "value"}

    def test_includes_all_fields_when_provided(self) -> None:
        """Should include all fields when provided with truthy values."""
        from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPWorkflowJobTemplateExecutorParameters

        config = AAPWorkflowJobTemplateExecutorParameters(
            workflow_job_template_id=1,
            extra_vars={"foo": "bar"},
            limit="host1",
            tags="deploy",
            skip_tags="skip",
            scm_branch="main",
        )
        body = _build_launch_body(config, inventory_id=99)

        assert body == {
            "inventory": 99,
            "extra_vars": {"foo": "bar"},
            "limit": "host1",
            "job_tags": "deploy",  # Mapped from "tags"
            "skip_tags": "skip",
            "scm_branch": "main",
        }


class TestWorkflowValidateConfig:
    """Tests for _validate_config helper."""

    def test_validate_config_success(self) -> None:
        from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import _validate_config

        config = _validate_config({"workflow_job_template_id": 42})
        assert config.workflow_job_template_id == 42

    def test_validate_config_failure(self) -> None:
        from syntara.workflows.workflow_engine.activities.aap_workflow_job_template_activity import _validate_config

        with pytest.raises(ApplicationError) as exc_info:
            _validate_config({"invalid_field_only": True})
        assert exc_info.value.type == "ConfigError"


_AUDIT_PATCH = "syntara.workflows.audit.aap_job_execution.AuditEventDispatcher"


class TestWorkflowAuditEventIntegration:
    """Tests for audit event dispatch in the main workflow activity function."""

    @pytest.mark.asyncio
    async def test_successful_execution_emits_launched_and_completed(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        status_response = create_workflow_workflow_job_status_response(workflow_job_id=123)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=status_response),
            patch(_AUDIT_PATCH) as mock_dispatcher,
        ):
            activity_config = build_activity_config(workflow_job_template_id=42)
            await execute_aap_workflow_job_template_activity(
                activity_config, None, execution_id="12345678-1234-5678-1234-567812345678"
            )

            assert mock_dispatcher.dispatch.call_count == 2
            from syntara.workflows.audit.aap_job_execution import AAPJobCompletedEvent, AAPJobLaunchedEvent

            call_args = [call.args[0] for call in mock_dispatcher.dispatch.call_args_list]
            assert isinstance(call_args[0], AAPJobLaunchedEvent)
            assert isinstance(call_args[1], AAPJobCompletedEvent)

    @pytest.mark.asyncio
    async def test_failed_execution_emits_launched_and_failed(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 456, "url": "/api/v2/workflow_jobs/456/"})
        failed_status = create_workflow_workflow_job_status_response(workflow_job_id=456, status="failed")
        activity_config = build_activity_config(workflow_job_template_id=42)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=failed_status),
            patch(_AUDIT_PATCH) as mock_dispatcher,
            pytest.raises(ApplicationError),
        ):
            await execute_aap_workflow_job_template_activity(
                activity_config, None, execution_id="12345678-1234-5678-1234-567812345678"
            )

        assert mock_dispatcher.dispatch.call_count == 2
        from syntara.workflows.audit.aap_job_execution import AAPJobFailedEvent, AAPJobLaunchedEvent

        call_args = [call.args[0] for call in mock_dispatcher.dispatch.call_args_list]
        assert isinstance(call_args[0], AAPJobLaunchedEvent)
        assert isinstance(call_args[1], AAPJobFailedEvent)

    @pytest.mark.asyncio
    async def test_no_audit_events_without_execution_id(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        status_response = create_workflow_workflow_job_status_response(workflow_job_id=123)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=status_response),
            patch(_AUDIT_PATCH) as mock_dispatcher,
        ):
            activity_config = build_activity_config(workflow_job_template_id=42)
            await execute_aap_workflow_job_template_activity(activity_config, None)
            mock_dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_unexpected_error_emits_failed_event(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        activity_config = build_activity_config(workflow_job_template_id=42)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            patch(_AUDIT_PATCH) as mock_dispatcher,
            pytest.raises(ApplicationError),
        ):
            await execute_aap_workflow_job_template_activity(
                activity_config, None, execution_id="12345678-1234-5678-1234-567812345678"
            )

        assert mock_dispatcher.dispatch.call_count == 2
        from syntara.workflows.audit.aap_job_execution import AAPJobFailedEvent, AAPJobLaunchedEvent

        call_args = [call.args[0] for call in mock_dispatcher.dispatch.call_args_list]
        assert isinstance(call_args[0], AAPJobLaunchedEvent)
        assert isinstance(call_args[1], AAPJobFailedEvent)
        assert call_args[1].error_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_cancelled_error_emits_failed_event(self, mock_activity_context: object) -> None:
        from temporalio.exceptions import CancelledError

        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/workflow_jobs/123/"})
        running_response = create_http_response(200, {"id": 123, "status": "running"})
        cancel_response = create_http_response(200, {})
        mock_is_cancelled = MagicMock(side_effect=[False, True])
        activity_config = build_activity_config(workflow_job_template_id=42)

        with (
            patch("temporalio.activity.is_cancelled", mock_is_cancelled),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=[launch_response, cancel_response]),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=running_response),
            patch(_AUDIT_PATCH) as mock_dispatcher,
            pytest.raises(CancelledError),
        ):
            await execute_aap_workflow_job_template_activity(
                activity_config, None, execution_id="12345678-1234-5678-1234-567812345678"
            )

        assert mock_dispatcher.dispatch.call_count == 2
        from syntara.workflows.audit.aap_job_execution import AAPJobFailedEvent, AAPJobLaunchedEvent

        call_args = [call.args[0] for call in mock_dispatcher.dispatch.call_args_list]
        assert isinstance(call_args[0], AAPJobLaunchedEvent)
        assert isinstance(call_args[1], AAPJobFailedEvent)
        assert call_args[1].job_status == "canceled"
