"""Unit tests for AAP job template activity (T005).

Tests AAP job template execution including:
- Basic job execution (success/failure)
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
from syntara.workflows.workflow_engine.activities.aap_job_template_activity import (
    execute_aap_job_template_activity,
)
from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

# Test constants
TEST_AAP_URL = "http://test.aap"
TEST_TOKEN = "test_token"  # noqa: S105
TEST_TOKEN_123 = "test_token_123"  # noqa: S105
TEST_USERNAME = "admin"
TEST_PASSWORD = "secret123"  # noqa: S105


def build_config(**kwargs: object) -> AAPJobTemplateExecutorParameters:
    """Helper to build configs using snake_case keys while keeping mypy happy."""
    return AAPJobTemplateExecutorParameters.model_validate(kwargs)


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


def create_job_status_response(
    job_id: int = 123,
    status: str = "successful",
    **overrides: object,
) -> httpx.Response:
    """Create a mock AAP job status response with sensible defaults.

    All fields can be overridden via keyword arguments.
    """
    data: dict[str, object] = {
        "id": job_id,
        "status": status,
        "artifacts": {},
        "created": "2026-04-23T20:10:58Z",
        "started": "2026-04-23T20:11:00Z",
        "finished": "2026-04-23T20:11:10Z",
        **overrides,
    }
    return create_http_response(200, data)


def create_successful_job_mocks(
    job_id: int = 123,
) -> dict[str, httpx.Response]:
    """Create standard mock responses for successful AAP job execution.

    Args:
        job_id: Job ID to use in responses

    Returns:
        Dictionary with 'launch' and 'status' response mocks

    """
    return {
        "launch": create_http_response(200, {"id": job_id, "url": f"/api/v2/jobs/{job_id}/"}),
        "status": create_job_status_response(job_id=job_id),
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


class TestAAPJobTemplateExecution:
    """Test AAP job template execution (basic flow)."""

    @pytest.mark.asyncio
    async def test_successful_job_execution(self, mock_activity_context: object) -> None:
        """Test successful job template launch and completion."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
        status_response = create_job_status_response(job_id=123, artifacts={"changed": 5, "ok": 10, "failed": 0})

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=status_response),
        ):
            activity_config = build_activity_config(
                job_template_id=42,
                inventory=123,
                extra_vars={"version": "1.0.0"},
            )

            result = await execute_aap_job_template_activity(activity_config, None)

            assert result["output"]["job_id"] == 123
            assert result["output"]["job_status"] == "successful"
            assert result["output"]["artifacts"]["changed"] == 5
            assert result["output"]["created"] == "2026-04-23T20:10:58Z"
            assert result["output"]["started"] == "2026-04-23T20:11:00Z"
            assert result["output"]["finished"] == "2026-04-23T20:11:10Z"

    @pytest.mark.asyncio
    async def test_successful_job_includes_job_url(self, mock_activity_context: object) -> None:
        """Test successful job output contains job_url pointing to AAP UI."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
        status_response = create_job_status_response(job_id=123)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=status_response),
        ):
            activity_config = build_activity_config(job_template_id=42)

            result = await execute_aap_job_template_activity(activity_config, None)

            assert result["output"]["job_url"] is not None
            assert "execution/jobs/playbook/123/output" in result["output"]["job_url"]

    @pytest.mark.asyncio
    async def test_failed_job_execution(self, mock_activity_context: object) -> None:
        """Test job template execution failure raises ApplicationError."""
        launch_response = create_http_response(200, {"id": 456, "url": "/api/v2/jobs/456/"})
        failed_status_response = create_job_status_response(job_id=456, status="failed")

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=failed_status_response),
            pytest.raises(ApplicationError) as exc_info,
        ):
            activity_config = build_activity_config(job_template_id=99)
            await execute_aap_job_template_activity(activity_config, None)

        assert exc_info.value.type == "AAPJobExecutionError"
        assert "456" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_failed_job_includes_job_url_in_error_details(self, mock_activity_context: object) -> None:
        """Test failed job error details include job_url."""
        launch_response = create_http_response(200, {"id": 456, "url": "/api/v2/jobs/456/"})
        failed_status_response = create_job_status_response(job_id=456, status="failed")

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=failed_status_response),
            pytest.raises(ApplicationError) as exc_info,
        ):
            activity_config = build_activity_config(job_template_id=99)
            await execute_aap_job_template_activity(activity_config, None)

        # ApplicationError details contain the output dict with job_url
        details = exc_info.value.details[0]
        assert details["output"]["job_url"] is not None
        assert "execution/jobs/playbook/456/output" in details["output"]["job_url"]

    @pytest.mark.asyncio
    async def test_canceled_job_raises_application_error(self, mock_activity_context: object) -> None:
        """Test canceled job raises ApplicationError with correct type."""
        launch_response = create_http_response(200, {"id": 456, "url": "/api/v2/jobs/456/"})
        canceled_status_response = create_job_status_response(job_id=456, status="canceled")
        activity_config = build_activity_config(job_template_id=99)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=canceled_status_response),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_aap_job_template_activity(activity_config, None)

        assert exc_info.value.type == "AAPJobExecutionError"
        assert "456" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_canceled_job_includes_job_url_in_error_details(self, mock_activity_context: object) -> None:
        """Test canceled job error details include job_url."""
        launch_response = create_http_response(200, {"id": 789, "url": "/api/v2/jobs/789/"})
        canceled_status_response = create_job_status_response(job_id=789, status="canceled")
        activity_config = build_activity_config(job_template_id=99)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=canceled_status_response),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_aap_job_template_activity(activity_config, None)

        details = exc_info.value.details[0]
        assert details["output"]["job_url"] is not None
        assert "execution/jobs/playbook/789/output" in details["output"]["job_url"]

    @pytest.mark.asyncio
    async def test_error_status_includes_job_url_in_error_details(self, mock_activity_context: object) -> None:
        """Test error status job error details include job_url."""
        launch_response = create_http_response(200, {"id": 789, "url": "/api/v2/jobs/789/"})
        error_status_response = create_job_status_response(job_id=789, status="error")
        activity_config = build_activity_config(job_template_id=99)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=error_status_response),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_aap_job_template_activity(activity_config, None)

        details = exc_info.value.details[0]
        assert details["output"]["job_url"] is not None
        assert "execution/jobs/playbook/789/output" in details["output"]["job_url"]

    @pytest.mark.asyncio
    async def test_unexpected_error_includes_job_url(self, mock_activity_context: object) -> None:
        """Test unexpected errors after launch include job_url in output."""
        launch_response = create_http_response(200, {"id": 321, "url": "/api/v2/jobs/321/"})
        activity_config = build_activity_config(job_template_id=42)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Unexpected"),
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_aap_job_template_activity(activity_config, None)

        details = exc_info.value.details[0]
        assert details["output"]["job_url"] is not None
        assert "execution/jobs/playbook/321/output" in details["output"]["job_url"]

    @pytest.mark.asyncio
    async def test_extra_vars_forwarded_to_aap(self, mock_activity_context: object) -> None:
        """Test extra_vars are forwarded correctly to AAP API.

        In V2, template expressions are resolved by the workflow engine before
        calling the activity. The activity receives already-resolved values.
        """
        launch_response = create_http_response(200, {"id": 789, "url": "/api/v2/jobs/789/"})

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_job_status_response(job_id=789),
            ),
        ):
            # V2: templates are resolved by dispatcher before reaching the activity
            activity_config = build_activity_config(
                job_template_id=42,
                extra_vars={
                    "app_version": "2.0.0",
                    "deploy_env": "staging",
                },
            )

            await execute_aap_job_template_activity(activity_config, None)

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
        launch_response = create_http_response(200, {"id": 890, "url": "/api/v2/jobs/890/"})

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_job_status_response(job_id=890),
            ),
        ):
            # V2: templates are resolved by dispatcher before reaching the activity
            activity_config = build_activity_config(
                job_template_id=42,
                extra_vars={
                    "hosts": [
                        {"name": "server1", "ip": "10.0.0.1", "port": 8080},
                        {"name": "server2", "ip": "10.0.0.2", "port": 8081},
                    ],
                    "parameters": {"timeout": 30, "retries": 3},
                },
            )

            await execute_aap_job_template_activity(activity_config, None)

            # Verify nested structures were resolved correctly
            call_body = mock_post.call_args.kwargs["json"]
            assert call_body["extra_vars"]["hosts"][0]["ip"] == "10.0.0.1"
            assert call_body["extra_vars"]["hosts"][0]["port"] == 8080
            assert call_body["extra_vars"]["hosts"][1]["ip"] == "10.0.0.2"
            assert call_body["extra_vars"]["hosts"][1]["port"] == 8081
            assert call_body["extra_vars"]["parameters"]["timeout"] == 30
            assert call_body["extra_vars"]["parameters"]["retries"] == 3


class TestAAPJobTemplateHeartbeat:
    """Test heartbeat functionality for long-running jobs."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    async def test_heartbeat_sent_during_polling(
        self,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test activity sends heartbeats during polling loop with STOP_MONITOR payload."""
        # Mock responses - multiple polling iterations (running → running → successful)
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
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
            mock_get.side_effect = [running_response_1, running_response_2, create_job_status_response()]

            activity_config = build_activity_config(job_template_id=42)

            await execute_aap_job_template_activity(activity_config, None)

            # Verify heartbeats were sent (initial + at least 2 during polling)
            assert mock_heartbeat.call_count >= 3

            # All heartbeat payloads should contain stop_monitor and partial_output
            for call_obj in mock_heartbeat.call_args_list:
                payload = call_obj[0][0]
                assert payload["stop_monitor"] is True
                assert "partial_output" in payload

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    async def test_heartbeat_after_launch_contains_job_id_and_url(
        self,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test the initial heartbeat after launch contains job_id and job_url in partial_output."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})

        mock_heartbeat = MagicMock()

        with (
            override_settings(**aap_settings_overrides),
            patch("temporalio.activity.heartbeat", mock_heartbeat),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_job_status_response(),
            ),
        ):
            activity_config = build_activity_config(job_template_id=42)

            await execute_aap_job_template_activity(activity_config, None)

            # The first heartbeat is sent immediately after launch (before polling)
            first_payload = mock_heartbeat.call_args_list[0][0][0]
            assert first_payload["stop_monitor"] is True
            partial = first_payload["partial_output"]
            assert partial["job_id"] == 123
            assert "execution/jobs/playbook/123/output" in partial["job_url"]


class TestAAPJobTemplateCancellation:
    """Test cancellation handling."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.heartbeat")
    async def test_cancel_aap_job_when_activity_cancelled(
        self,
        mock_heartbeat: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test AAP job is cancelled when activity is cancelled."""
        from temporalio.exceptions import CancelledError

        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
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

            activity_config = build_activity_config(job_template_id=42)

            # Should raise CancelledError
            with pytest.raises(CancelledError):
                await execute_aap_job_template_activity(activity_config, None)

            # Verify cancel endpoint was called (plural "jobs" as per AAP API)
            cancel_call = mock_post.call_args_list[1]
            assert "/jobs/123/cancel/" in str(cancel_call)


class TestAAPJobTemplateErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_launch_failure_authentication_error(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test job launch fails with authentication error."""
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
            activity_config = build_activity_config(job_template_id=42)

            with pytest.raises(ApplicationError, match="Failed to launch"):
                await execute_aap_job_template_activity(activity_config, None)

    @pytest.mark.asyncio
    async def test_launch_failure_template_not_found(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test job launch fails with 404 template not found raises ApplicationError."""
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
            activity_config = build_activity_config(job_template_id=999)

            with pytest.raises(ApplicationError, match="Failed to launch"):
                await execute_aap_job_template_activity(activity_config, None)

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
            activity_config = build_activity_config(job_template_id=42)

            with pytest.raises(ApplicationError, match="Failed to connect to AAP"):
                await execute_aap_job_template_activity(activity_config, None)

    @pytest.mark.asyncio
    async def test_invalid_config_missing_job_template_id(self) -> None:
        """Test error with missing job_template_id raises ApplicationError."""
        activity_config: dict[str, object] = {}  # Missing job_template_id

        with pytest.raises(ApplicationError) as exc_info:
            await execute_aap_job_template_activity(activity_config, None)
        assert exc_info.value.type == "ConfigError"


class TestAAPJobTemplateTimeout:
    """Test timeout handling for long-running jobs."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_job_timeout_during_polling(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        override_runtime_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test job execution timeout is enforced during polling."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
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
            activity_config = build_activity_config(job_template_id=42)
            activity_config[constants.ENGINE_TIMEOUT_SECONDS_KEY] = 10

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_job_template_activity(activity_config, None)
            assert "timed out after 10 seconds" in str(exc_info.value)
            assert "123" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_job_completes_within_timeout(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test job completes successfully when it finishes before timeout."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
        running_response = create_http_response(200, {"id": 123, "status": "running"})

        # Mock time to show job completes within timeout
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
            mock_get.side_effect = [running_response, create_job_status_response()]

            # Configure timeout of 10 seconds (job completes in ~2 seconds)
            activity_config = build_activity_config(job_template_id=42, timeout=10)

            result = await execute_aap_job_template_activity(activity_config, None)

            # Job should complete successfully
            assert result["output"]["job_status"] == "successful"
            assert result["output"]["job_id"] == 123


class TestAAPJobTemplatePollResilience:
    """Test transient poll error resilience and timeout messages."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_poll_failure_consecutive_cap_message(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        aap_settings_overrides: dict[str, object],
    ) -> None:
        """Test that persistent poll errors trigger the consecutive error cap before timeout."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})

        # Every poll returns 503 — the consecutive error cap (5) should fire
        # before the generous timeout (3600s) expires.
        poll_error = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(503),
        )

        with (
            override_settings(**aap_settings_overrides),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=poll_error),
        ):
            activity_config = build_activity_config(job_template_id=42)
            activity_config[constants.ENGINE_TIMEOUT_SECONDS_KEY] = 3600

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_job_template_activity(activity_config, None)
            assert "launched successfully but unable to determine completion status" in str(exc_info.value)
            assert "polling failed 5 consecutive times" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_poll_failure_timeout_with_last_error_message(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that timeout during poll errors produces the 'polling failed repeatedly until timeout' message."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})

        poll_error = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(503),
        )

        # We need at least one poll error before timeout fires so that
        # last_poll_error is set. Use a list long enough to cover all
        # time.time() calls across both modules (activity start_time +
        # poll loop elapsed checks). The sequence:
        #   call 1: activity start_time = 0.0
        #   call 2: poll loop elapsed = 0.0 (passes, poll fails -> last_poll_error set)
        #   call 3: poll loop elapsed = 11.0 (exceeds effective_timeout=9 -> timeout with error)
        # Extra values ensure no StopIteration from unexpected callers.
        fake_time = MagicMock(side_effect=[0.0, 0.0, 11.0] + [11.0] * 20)

        with (
            override_settings(**build_aap_settings_overrides(poll_interval=0.01, timeout=10)),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=poll_error),
            patch(
                "syntara.workflows.workflow_engine.activities.aap_job_template_activity.time",
                time=fake_time,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.aap_common.time",
                time=fake_time,
            ),
        ):
            activity_config = build_activity_config(job_template_id=42)
            activity_config[constants.ENGINE_TIMEOUT_SECONDS_KEY] = 10

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_job_template_activity(activity_config, None)
            assert "polling failed repeatedly until timeout (10s)" in str(exc_info.value)
            assert "Last error:" in str(exc_info.value)


class TestAAPJobTemplateAuthentication:
    """Test authentication handling."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_token_authentication(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test AAP token authentication is used."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})

        with (
            override_settings(**build_aap_settings_overrides(token=TEST_TOKEN_123)),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_job_status_response(),
            ),
        ):
            activity_config = build_activity_config(job_template_id=42)

            await execute_aap_job_template_activity(activity_config, None)

            # Verify Authorization header with Bearer token
            assert "headers" in mock_post.call_args.kwargs
            assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer test_token_123"

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_basic_authentication(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test AAP basic authentication is used."""
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})

        with (
            override_settings(
                **build_aap_settings_overrides(token=None, username=TEST_USERNAME, password=TEST_PASSWORD)
            ),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_job_status_response(),
            ),
        ):
            activity_config = build_activity_config(job_template_id=42)

            await execute_aap_job_template_activity(activity_config, None)

            # Verify BasicAuth was used
            assert "auth" in mock_post.call_args.kwargs
            assert isinstance(mock_post.call_args.kwargs["auth"], httpx.BasicAuth)

    @pytest.mark.asyncio
    async def test_aap_activity_with_pre_resolved_parameters(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test AAP activity receives pre-resolved config (v2: dispatcher resolves templates)."""
        launch_response = create_http_response(201, {"id": 123, "url": "/api/v2/jobs/123/"})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("temporalio.activity.is_cancelled", return_value=False),
            patch("temporalio.activity.heartbeat"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response) as mock_post,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=create_job_status_response(),
            ),
        ):
            # V2: flat config with already-resolved values
            activity_config = build_activity_config(job_template_id=42, verbosity=2)

            await execute_aap_job_template_activity(activity_config, None)

            # Verify resolved values were used
            post_body = mock_post.call_args.kwargs["json"]
            assert post_body["verbosity"] == 2


class TestAAPJobTemplateNameBasedReference:
    """Test name-based job template references."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_successful_name_based_execution(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test successful job execution using name-based reference."""
        mocks = create_successful_job_mocks(job_id=123)

        # Mock lookup response
        lookup_response = create_http_response(200, {"count": 1, "results": [{"id": 42, "name": "Deploy App"}]})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            # GET calls: lookup, status, output
            mock_get.side_effect = [lookup_response, mocks["status"]]

            activity_config = build_activity_config(
                job_template_name="Deploy App",
                organization_name="Default",
                extra_vars={"version": "1.0.0"},
            )

            result = await execute_aap_job_template_activity(activity_config, None)

            assert result["output"]["job_id"] == 123
            assert result["output"]["job_status"] == "successful"

            # Verify lookup was called with correct params
            lookup_call = mock_get.call_args_list[0]
            assert "job_templates" in str(lookup_call.args[0])
            assert lookup_call.kwargs["params"]["name"] == "Deploy App"
            assert lookup_call.kwargs["params"]["organization__name"] == "Default"

            # Verify POST was called with numeric ID (not named URL)
            post_url = mock_post.call_args.args[0]
            assert "/job_templates/42/launch/" in post_url

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
                job_template_name="Nonexistent Template",
                organization_name="Default",
            )

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_job_template_activity(activity_config, None)
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
                    {"id": 42, "name": "Deploy App"},
                    {"id": 43, "name": "Deploy App"},
                ],
            },
        )

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=lookup_response),
        ):
            activity_config = build_activity_config(
                job_template_name="Deploy App",
                organization_name="Default",
            )

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_job_template_activity(activity_config, None)
            assert "Multiple job templates" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("config_kwargs", "should_pass", "error_match"),
        [
            # Valid cases - should pass
            ({"job_template_id": 42}, True, None),
            ({"job_template_name": "Deploy", "organization_name": "Default"}, True, None),
            ({"job_template_name": "  Deploy  ", "organization_name": "  Default  "}, True, None),
            # Both ID and name is valid - ID takes precedence
            ({"job_template_id": 42, "job_template_name": "Deploy", "organization_name": "Default"}, True, None),
            # Invalid cases - should raise ValidationError
            ({"job_template_name": "Deploy"}, False, "organization_name is required when using job_template_name"),
            ({"organization_name": "Default"}, False, "job_template_id or job_template_name"),
            ({"extra_vars": {"foo": "bar"}}, False, "job_template_id or job_template_name"),
            ({"job_template_name": "", "organization_name": "Default"}, False, "job_template_id or job_template_name"),
            (
                {"job_template_name": "Deploy", "organization_name": ""},
                False,
                "organization_name is required when using job_template_name",
            ),
            # V2 model strips whitespace; whitespace-only names are accepted as empty
            # and caught at execution time, not validation time
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
            if "job_template_id" in config_kwargs:
                assert config.job_template_id == config_kwargs["job_template_id"]
            if "job_template_name" in config_kwargs:
                assert config.job_template_name == config_kwargs["job_template_name"]
            if "organization_name" in config_kwargs:
                assert config.organization_name == config_kwargs["organization_name"]
        else:
            with pytest.raises(ValidationError, match=error_match):
                build_config(**config_kwargs)

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_pre_resolved_name_based_references(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test name-based references with pre-resolved values (v2: dispatcher resolves templates)."""
        mocks = create_successful_job_mocks(job_id=888)

        # Mock lookup response
        lookup_response = create_http_response(200, {"count": 1, "results": [{"id": 55, "name": "Dynamic Template"}]})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            # GET calls: lookup, status, output
            mock_get.side_effect = [lookup_response, mocks["status"]]

            # V2: dispatcher already resolved template expressions
            activity_config = build_activity_config(
                job_template_name="Dynamic Template",
                organization_name="Production",
            )

            result = await execute_aap_job_template_activity(activity_config, None)
            assert result["output"]["job_id"] == 888

            # Verify lookup was called with resolved names
            lookup_call = mock_get.call_args_list[0]
            assert lookup_call.kwargs["params"]["name"] == "Dynamic Template"
            assert lookup_call.kwargs["params"]["organization__name"] == "Production"

            # Verify POST was called with numeric ID
            post_url = mock_post.call_args.args[0]
            assert "/job_templates/55/launch/" in post_url

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_backwards_compatibility_id_based(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that ID-based references still work (backwards compatibility)."""
        mocks = create_successful_job_mocks(job_id=999)

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = [mocks["status"]]

            # Use old ID-based config
            activity_config = build_activity_config(job_template_id=42)

            result = await execute_aap_job_template_activity(activity_config, None)
            assert result["output"]["job_id"] == 999

            # Verify POST was called with numeric ID in path (not named URL)
            post_url = mock_post.call_args.args[0]
            assert "/job_templates/42/launch/" in post_url
            assert "++" not in post_url  # No named URL separator

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_id_takes_precedence_over_name(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that job_template_id takes precedence over job_template_name when both are provided."""
        mocks = create_successful_job_mocks(job_id=777)

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            # Only status and output calls - no lookup should happen
            mock_get.side_effect = [mocks["status"]]

            # Provide both ID and name - ID should take precedence
            activity_config = build_activity_config(
                job_template_id=42,
                job_template_name="Ignored Template",
                organization_name="Ignored Org",
            )

            result = await execute_aap_job_template_activity(activity_config, None)
            assert result["output"]["job_id"] == 777

            # Verify POST was called with ID 42 (not name lookup)
            post_url = mock_post.call_args.args[0]
            assert "/job_templates/42/launch/" in post_url

            # Verify no lookup was performed (only 1 GET call: status, not 2)
            assert mock_get.call_count == 1


class TestAAPInventoryNameBasedReference:
    """Test name-based inventory references."""

    @pytest.mark.parametrize(
        ("config_kwargs", "should_pass", "error_match"),
        [
            # Valid cases
            ({"job_template_id": 42, "inventory_id": 123}, True, None),
            ({"job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"}, True, None),
            ({"job_template_id": 42}, True, None),  # No inventory is optional
            # Both ID and name is valid - ID takes precedence
            (
                {"job_template_id": 42, "inventory_id": 123, "inventory_name": "Prod", "organization_name": "Default"},
                True,
                None,
            ),
            # Invalid cases
            (
                {"job_template_id": 42, "inventory_name": "Prod"},
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
    async def test_inventory_name_lookup_and_job_execution(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test successful inventory lookup by name and job execution."""
        mocks = create_successful_job_mocks(job_id=456)
        inventory_lookup = create_http_response(200, {"count": 1, "results": [{"id": 789, "name": "Production"}]})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = [inventory_lookup, mocks["status"]]

            activity_config = build_activity_config(
                job_template_id=42,
                inventory_name="Production",
                organization_name="Default",
            )

            result = await execute_aap_job_template_activity(activity_config, None)

            assert result["output"]["job_id"] == 456
            assert result["output"]["job_status"] == "successful"
            # Verify inventory lookup
            assert "inventories" in str(mock_get.call_args_list[0].args[0])
            # Verify resolved inventory ID in POST body
            assert mock_post.call_args.kwargs["json"]["inventory"] == 789

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_combined_job_template_and_inventory_name_lookup(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test both job template and inventory using name-based lookups share organization."""
        mocks = create_successful_job_mocks(job_id=666)
        jt_lookup = create_http_response(200, {"count": 1, "results": [{"id": 111, "name": "Deploy"}]})
        inv_lookup = create_http_response(200, {"count": 1, "results": [{"id": 222, "name": "Staging"}]})

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = [jt_lookup, inv_lookup, mocks["status"]]

            activity_config = build_activity_config(
                job_template_name="Deploy",
                inventory_name="Staging",
                organization_name="Default",
            )

            result = await execute_aap_job_template_activity(activity_config, None)

            assert result["output"]["job_status"] == "successful"
            # Verify both lookups used same organization
            assert mock_get.call_args_list[0].kwargs["params"]["organization__name"] == "Default"
            assert mock_get.call_args_list[1].kwargs["params"]["organization__name"] == "Default"
            # Verify POST used both resolved IDs
            assert "/job_templates/111/launch/" in mock_post.call_args.args[0]
            assert mock_post.call_args.kwargs["json"]["inventory"] == 222

    @pytest.mark.parametrize(
        ("lookup_results", "error_match"),
        [
            ({"count": 0, "results": []}, "Inventory 'Missing' not found"),
            ({"count": 2, "results": [{"id": 1, "name": "Dup"}, {"id": 2, "name": "Dup"}]}, "Multiple inventories"),
        ],
    )
    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_inventory_lookup_error_cases(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        lookup_results: dict[str, Any],
        error_match: str,
    ) -> None:
        """Test inventory lookup errors (not found, multiple found)."""
        with (
            override_settings(**build_aap_settings_overrides()),
            patch(
                "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=create_http_response(200, lookup_results)
            ),
        ):
            activity_config = build_activity_config(
                job_template_id=42,
                inventory_name="Missing" if "not found" in error_match else "Dup",
                organization_name="Default",
            )

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_job_template_activity(activity_config, None)
            assert error_match in str(exc_info.value)

    @pytest.mark.parametrize(
        ("resource_type", "config_kwargs", "status_code", "error_match"),
        [
            # Job template lookup HTTP errors
            ("job_template", {"job_template_name": "Deploy", "organization_name": "Default"}, 401, "Failed to lookup"),
            ("job_template", {"job_template_name": "Deploy", "organization_name": "Default"}, 403, "Failed to lookup"),
            ("job_template", {"job_template_name": "Deploy", "organization_name": "Default"}, 404, "Failed to lookup"),
            ("job_template", {"job_template_name": "Deploy", "organization_name": "Default"}, 500, "Failed to lookup"),
            # Inventory lookup HTTP errors
            (
                "inventory",
                {"job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"},
                401,
                "Failed to lookup",
            ),
            (
                "inventory",
                {"job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"},
                403,
                "Failed to lookup",
            ),
            (
                "inventory",
                {"job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"},
                500,
                "Failed to lookup",
            ),
        ],
        ids=[
            "job_template_401_unauthorized",
            "job_template_403_forbidden",
            "job_template_404_not_found",
            "job_template_500_server_error",
            "inventory_401_unauthorized",
            "inventory_403_forbidden",
            "inventory_500_server_error",
        ],
    )
    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_lookup_http_status_errors(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        resource_type: str,
        config_kwargs: dict[str, Any],
        status_code: int,
        error_match: str,
    ) -> None:
        """Test HTTP status errors during resource lookup (job template or inventory)."""
        with (
            override_settings(**build_aap_settings_overrides()),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    f"{status_code} Error",
                    request=MagicMock(),
                    response=create_http_response(status_code, text=f"Error {status_code}"),
                ),
            ),
        ):
            activity_config = build_activity_config(**config_kwargs)

            with pytest.raises(ApplicationError) as exc_info:
                await execute_aap_job_template_activity(activity_config, None)
            assert error_match in str(exc_info.value)

    @pytest.mark.parametrize(
        ("resource_type", "config_kwargs", "error_type", "error_message", "error_match"),
        [
            # Job template lookup connection errors
            (
                "job_template",
                {"job_template_name": "Deploy", "organization_name": "Default"},
                httpx.ConnectError,
                "Connection refused",
                "Failed to connect to AAP",
            ),
            (
                "job_template",
                {"job_template_name": "Deploy", "organization_name": "Default"},
                httpx.TimeoutException,
                "Request timeout",
                "Failed to connect to AAP",
            ),
            (
                "job_template",
                {"job_template_name": "Deploy", "organization_name": "Default"},
                httpx.NetworkError,
                "Network unreachable",
                "Failed to connect to AAP",
            ),
            # Inventory lookup connection errors
            (
                "inventory",
                {"job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"},
                httpx.ConnectError,
                "Connection refused",
                "Failed to connect to AAP",
            ),
            (
                "inventory",
                {"job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"},
                httpx.TimeoutException,
                "Request timeout",
                "Failed to connect to AAP",
            ),
            (
                "inventory",
                {"job_template_id": 42, "inventory_name": "Prod", "organization_name": "Default"},
                httpx.NetworkError,
                "Network unreachable",
                "Failed to connect to AAP",
            ),
        ],
        ids=[
            "job_template_connect_error",
            "job_template_timeout_error",
            "job_template_network_error",
            "inventory_connect_error",
            "inventory_timeout_error",
            "inventory_network_error",
        ],
    )
    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_lookup_connection_errors(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
        resource_type: str,
        config_kwargs: dict[str, Any],
        error_type: type[httpx.HTTPError],
        error_message: str,
        error_match: str,
    ) -> None:
        """Test connection errors during resource lookup (job template or inventory)."""
        with (
            override_settings(**build_aap_settings_overrides()),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                side_effect=error_type(error_message),
            ),
        ):
            activity_config = build_activity_config(**config_kwargs)

            with pytest.raises(ApplicationError, match=error_match):
                await execute_aap_job_template_activity(activity_config, None)

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_inventory_id_takes_precedence_over_name(
        self,
        mock_heartbeat: object,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that inventory_id takes precedence over inventory_name when both are provided."""
        mocks = create_successful_job_mocks(job_id=888)

        with (
            override_settings(**build_aap_settings_overrides()),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mocks["launch"]) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            # Only status and output calls - no inventory lookup should happen
            mock_get.side_effect = [mocks["status"]]

            # Provide both inventory_id and inventory_name - ID should take precedence
            activity_config = build_activity_config(
                job_template_id=42,
                inventory_id=555,
                inventory_name="Ignored Inventory",
                organization_name="Ignored Org",
            )

            result = await execute_aap_job_template_activity(activity_config, None)
            assert result["output"]["job_id"] == 888

            # Verify POST body used inventory ID 555 (not name lookup)
            post_body = mock_post.call_args.kwargs["json"]
            assert post_body["inventory"] == 555

            # Verify no inventory lookup was performed (only 1 GET call: status)
            assert mock_get.call_count == 1


class TestBuildLaunchBody:
    """Unit tests for _build_launch_body helper function."""

    def test_includes_inventory_when_provided(self) -> None:
        """Should include inventory ID in body when provided."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

        config = AAPJobTemplateExecutorParameters(job_template_id=1)
        body = _build_launch_body(config, inventory_id=42)

        assert body["inventory"] == 42

    def test_skips_inventory_when_none(self) -> None:
        """Should not include inventory in body when None."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

        config = AAPJobTemplateExecutorParameters(job_template_id=1)
        body = _build_launch_body(config, inventory_id=None)

        assert "inventory" not in body

    def test_includes_verbosity_zero(self) -> None:
        """Should include verbosity=0 (NORMAL level) in body."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters
        from syntara.workflows.workflow_engine.models.workflow_definition import AAPVerbosity

        config = AAPJobTemplateExecutorParameters(job_template_id=1, verbosity=AAPVerbosity.NORMAL)
        body = _build_launch_body(config, inventory_id=None)

        assert body["verbosity"] == AAPVerbosity.NORMAL

    def test_skips_empty_job_credentials_list(self) -> None:
        """Should not include credentials when empty list."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

        config = AAPJobTemplateExecutorParameters(job_template_id=1, job_credentials=[])
        body = _build_launch_body(config, inventory_id=None)

        assert "credentials" not in body

    def test_includes_non_empty_job_credentials_list(self) -> None:
        """Should include credentials in AAP API body when job_credentials provided."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

        config = AAPJobTemplateExecutorParameters(job_template_id=1, job_credentials=[1, 2, 3])
        body = _build_launch_body(config, inventory_id=None)

        assert body["credentials"] == [1, 2, 3]

    def test_accepts_job_credentials_field(self) -> None:
        """Should accept job_credentials field directly."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

        config = AAPJobTemplateExecutorParameters.model_validate({"job_template_id": 1, "job_credentials": [5, 6]})
        body = _build_launch_body(config, inventory_id=None)

        assert body["credentials"] == [5, 6]

    def test_skips_empty_extra_vars_dict(self) -> None:
        """Should not include extra_vars when empty dict."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

        config = AAPJobTemplateExecutorParameters(job_template_id=1, extra_vars={})
        body = _build_launch_body(config, inventory_id=None)

        assert "extra_vars" not in body

    def test_includes_non_empty_extra_vars_dict(self) -> None:
        """Should include extra_vars when non-empty dict."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters

        config = AAPJobTemplateExecutorParameters(job_template_id=1, extra_vars={"key": "value"})
        body = _build_launch_body(config, inventory_id=None)

        assert body["extra_vars"] == {"key": "value"}

    def test_includes_all_fields_when_provided(self) -> None:
        """Should include all fields when provided with truthy values."""
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _build_launch_body
        from syntara.workflows.workflow_engine.models import AAPJobTemplateExecutorParameters
        from syntara.workflows.workflow_engine.models.workflow_definition import AAPJobType, AAPVerbosity

        config = AAPJobTemplateExecutorParameters(
            job_template_id=1,
            job_credentials=[1],
            extra_vars={"foo": "bar"},
            limit="host1",
            tags="deploy",
            skip_tags="skip",
            verbosity=AAPVerbosity.VERBOSE,
            job_type=AAPJobType.RUN,
            forks=10,
            job_slicing=2,
            diff_mode=True,
        )
        body = _build_launch_body(config, inventory_id=99)

        assert body == {
            "inventory": 99,
            "credentials": [1],
            "extra_vars": {"foo": "bar"},
            "limit": "host1",
            "job_tags": "deploy",  # Mapped from "tags"
            "skip_tags": "skip",
            "verbosity": AAPVerbosity.VERBOSE,
            "job_type": AAPJobType.RUN,
            "forks": 10,
            "job_slice_count": 2,  # Mapped from "job_slicing"
            "diff_mode": True,
        }


class TestValidateConfig:
    """Tests for _validate_config helper."""

    def test_validate_config_success(self) -> None:
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _validate_config

        config = _validate_config({"job_template_id": 42})
        assert config.job_template_id == 42

    def test_validate_config_failure(self) -> None:
        from syntara.workflows.workflow_engine.activities.aap_job_template_activity import _validate_config

        with pytest.raises(ApplicationError) as exc_info:
            _validate_config({"invalid_field_only": True})
        assert exc_info.value.type == "ConfigError"


_AUDIT_PATCH = "syntara.workflows.audit.aap_job_execution.AuditEventDispatcher"


class TestAuditEventIntegration:
    """Tests for audit event dispatch in the main activity function."""

    @pytest.mark.asyncio
    async def test_successful_execution_emits_launched_and_completed(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
        status_response = create_job_status_response(job_id=123)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=status_response),
            patch(_AUDIT_PATCH) as mock_dispatcher,
        ):
            activity_config = build_activity_config(job_template_id=42)
            await execute_aap_job_template_activity(
                activity_config, None, execution_id="12345678-1234-5678-1234-567812345678"
            )

            assert mock_dispatcher.dispatch.call_count == 2
            from syntara.workflows.audit.aap_job_execution import AAPJobCompletedEvent, AAPJobLaunchedEvent

            call_args = [call.args[0] for call in mock_dispatcher.dispatch.call_args_list]
            assert isinstance(call_args[0], AAPJobLaunchedEvent)
            assert isinstance(call_args[1], AAPJobCompletedEvent)

    @pytest.mark.asyncio
    async def test_failed_execution_emits_launched_and_failed(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 456, "url": "/api/v2/jobs/456/"})
        failed_status = create_job_status_response(job_id=456, status="failed")
        activity_config = build_activity_config(job_template_id=42)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=failed_status),
            patch(_AUDIT_PATCH) as mock_dispatcher,
            pytest.raises(ApplicationError),
        ):
            await execute_aap_job_template_activity(
                activity_config, None, execution_id="12345678-1234-5678-1234-567812345678"
            )

        assert mock_dispatcher.dispatch.call_count == 2
        from syntara.workflows.audit.aap_job_execution import AAPJobFailedEvent, AAPJobLaunchedEvent

        call_args = [call.args[0] for call in mock_dispatcher.dispatch.call_args_list]
        assert isinstance(call_args[0], AAPJobLaunchedEvent)
        assert isinstance(call_args[1], AAPJobFailedEvent)

    @pytest.mark.asyncio
    async def test_no_audit_events_without_execution_id(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
        status_response = create_job_status_response(job_id=123)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=status_response),
            patch(_AUDIT_PATCH) as mock_dispatcher,
        ):
            activity_config = build_activity_config(job_template_id=42)
            await execute_aap_job_template_activity(activity_config, None)
            mock_dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_unexpected_error_emits_failed_event(self, mock_activity_context: object) -> None:
        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
        activity_config = build_activity_config(job_template_id=42)

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=launch_response),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            patch(_AUDIT_PATCH) as mock_dispatcher,
            pytest.raises(ApplicationError),
        ):
            await execute_aap_job_template_activity(
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

        launch_response = create_http_response(200, {"id": 123, "url": "/api/v2/jobs/123/"})
        running_response = create_http_response(200, {"id": 123, "status": "running"})
        cancel_response = create_http_response(200, {})
        mock_is_cancelled = MagicMock(side_effect=[False, True])
        activity_config = build_activity_config(job_template_id=42)

        with (
            patch("temporalio.activity.is_cancelled", mock_is_cancelled),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=[launch_response, cancel_response]),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=running_response),
            patch(_AUDIT_PATCH) as mock_dispatcher,
            pytest.raises(CancelledError),
        ):
            await execute_aap_job_template_activity(
                activity_config, None, execution_id="12345678-1234-5678-1234-567812345678"
            )

        assert mock_dispatcher.dispatch.call_count == 2
        from syntara.workflows.audit.aap_job_execution import AAPJobFailedEvent, AAPJobLaunchedEvent

        call_args = [call.args[0] for call in mock_dispatcher.dispatch.call_args_list]
        assert isinstance(call_args[0], AAPJobLaunchedEvent)
        assert isinstance(call_args[1], AAPJobFailedEvent)
        assert call_args[1].job_status == "canceled"
