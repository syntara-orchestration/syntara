"""Tests for AAP polling resilience and transient error handling."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from syntara.workflows.workflow_engine.activities.aap_common import (
    MAX_CONSECUTIVE_POLL_ERRORS,
    AAPActivityExecutionError,
    _is_transient_poll_error,
    _TransientPollError,
    build_aap_job_url,
    poll_until_complete,
)
from syntara.workflows.workflow_engine.activities.common import (
    HEARTBEAT_PARTIAL_OUTPUT_KEY,
    HEARTBEAT_STOP_MONITOR,
)


class TestIsTransientPollError:
    """Test _is_transient_poll_error classification."""

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
    def test_retryable_http_status_is_transient(self, status_code: int) -> None:
        exc = httpx.HTTPStatusError(
            f"{status_code}",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(status_code),
        )
        assert _is_transient_poll_error(exc) is True

    def test_404_is_not_transient(self) -> None:
        exc = httpx.HTTPStatusError(
            "404",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(404),
        )
        assert _is_transient_poll_error(exc) is False

    @pytest.mark.parametrize("status_code", [401, 403, 400])
    def test_non_retryable_http_status_is_not_transient(self, status_code: int) -> None:
        exc = httpx.HTTPStatusError(
            f"{status_code}",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(status_code),
        )
        assert _is_transient_poll_error(exc) is False

    def test_connect_error_is_transient(self) -> None:
        exc = httpx.ConnectError("Connection refused")
        assert _is_transient_poll_error(exc) is True

    def test_timeout_exception_is_transient(self) -> None:
        exc = httpx.ReadTimeout("Read timed out")
        assert _is_transient_poll_error(exc) is True

    def test_generic_http_error_is_not_transient(self) -> None:
        exc = httpx.HTTPError("Some other error")
        assert _is_transient_poll_error(exc) is False


class TestTransientPollError:
    """Test _TransientPollError sentinel exception."""

    def test_is_exception(self) -> None:
        assert issubclass(_TransientPollError, Exception)

    def test_carries_message(self) -> None:
        err = _TransientPollError("poll failed: 503")
        assert "503" in str(err)


class TestAAPActivityExecutionErrorRetryable:
    """Test retryable flag on AAPActivityExecutionError."""

    def test_default_not_retryable(self) -> None:
        err = AAPActivityExecutionError("fail")
        assert err.retryable is False

    def test_explicit_retryable(self) -> None:
        err = AAPActivityExecutionError("transient", retryable=True)
        assert err.retryable is True

    def test_explicit_not_retryable(self) -> None:
        err = AAPActivityExecutionError("permanent", retryable=False)
        assert err.retryable is False


class TestBuildAAPJobUrl:
    """Test build_aap_job_url helper function."""

    def test_playbook_job_url(self) -> None:
        """Test default playbook job type URL."""
        url = build_aap_job_url("https://aap.example.com", 123)
        assert url == "https://aap.example.com/execution/jobs/playbook/123/output"

    def test_workflow_job_url(self) -> None:
        """Test workflow job type URL."""
        url = build_aap_job_url("https://aap.example.com", 456, job_type="workflow")
        assert url == "https://aap.example.com/execution/jobs/workflow/456/output"

    def test_custom_job_type(self) -> None:
        """Test custom job type URL."""
        url = build_aap_job_url("https://aap.example.com", 789, job_type="custom")
        assert url == "https://aap.example.com/execution/jobs/custom/789/output"

    def test_strips_no_trailing_slash(self) -> None:
        """Test URL construction with base URL without trailing slash."""
        url = build_aap_job_url("https://aap.example.com", 100)
        assert url == "https://aap.example.com/execution/jobs/playbook/100/output"

    def test_base_url_with_trailing_slash(self) -> None:
        """Test URL construction strips trailing slash from base URL."""
        url = build_aap_job_url("https://aap.example.com/", 100)
        assert url == "https://aap.example.com/execution/jobs/playbook/100/output"


class TestPollUntilCompleteHeartbeat:
    """Test heartbeat payloads in poll_until_complete include STOP_MONITOR and partial_output."""

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_heartbeat_includes_stop_monitor_and_partial_output(
        self,
        mock_heartbeat: MagicMock,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test heartbeats during polling carry STOP_MONITOR and partial_output."""
        running_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={"id": 42, "status": "running"},
        )
        successful_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={
                "id": 42,
                "status": "successful",
                "artifacts": {},
                "created": "",
                "started": "",
                "finished": "",
            },
        )

        partial_output: dict[str, Any] = {
            "job_id": 42,
            "job_url": "https://aap.example.com/execution/jobs/playbook/42/output",
        }

        # Mock time.time() to return controlled values within timeout
        start_time = 1000.0
        time_counter = {"value": start_time}

        def mock_time() -> float:
            current = time_counter["value"]
            time_counter["value"] += 1.0
            return current

        with (
            override_settings(
                aap_base_url="https://aap.example.com",
                aap_poll_interval_seconds=0.01,
                aap_timeout_seconds=30,
                aap_token=SecretStr("tok"),
                aap_username=None,
                aap_password=None,
            ),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("time.time", side_effect=mock_time),
        ):
            mock_get.side_effect = [running_response, successful_response]

            from syntara.core.config.base import get_settings

            settings = get_settings()

            result = await poll_until_complete(
                client=httpx.AsyncClient(),
                settings=settings,
                job_id=42,
                auth_headers={"Authorization": "Bearer tok"},
                basic_auth=None,
                base_url="https://aap.example.com",
                timeout_seconds=30,
                start_time=start_time,
                job_type="jobs",
                terminal_statuses={"successful", "failed", "error", "canceled"},
                error_class=AAPActivityExecutionError,
                partial_output=partial_output,
            )

        assert result["status"] == "successful"
        # Verify heartbeat was called with the structured payload
        assert mock_heartbeat.call_count >= 1
        for call_obj in mock_heartbeat.call_args_list:
            payload = call_obj[0][0]
            assert payload[HEARTBEAT_STOP_MONITOR] is True
            assert payload[HEARTBEAT_PARTIAL_OUTPUT_KEY] == partial_output

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_heartbeat_with_none_partial_output(
        self,
        mock_heartbeat: MagicMock,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test heartbeats carry None partial_output when not provided."""
        running_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={"id": 42, "status": "running"},
        )
        successful_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={
                "id": 42,
                "status": "successful",
                "artifacts": {},
                "created": "",
                "started": "",
                "finished": "",
            },
        )

        start_time = 1000.0
        time_counter = {"value": start_time}

        def mock_time() -> float:
            current = time_counter["value"]
            time_counter["value"] += 1.0
            return current

        with (
            override_settings(
                aap_base_url="https://aap.example.com",
                aap_poll_interval_seconds=0.01,
                aap_timeout_seconds=30,
                aap_token=SecretStr("tok"),
                aap_username=None,
                aap_password=None,
            ),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("time.time", side_effect=mock_time),
        ):
            mock_get.side_effect = [running_response, successful_response]

            from syntara.core.config.base import get_settings

            settings = get_settings()

            await poll_until_complete(
                client=httpx.AsyncClient(),
                settings=settings,
                job_id=42,
                auth_headers={"Authorization": "Bearer tok"},
                basic_auth=None,
                base_url="https://aap.example.com",
                timeout_seconds=30,
                start_time=start_time,
                job_type="jobs",
                terminal_statuses={"successful", "failed", "error", "canceled"},
                error_class=AAPActivityExecutionError,
                partial_output=None,
            )

        assert mock_heartbeat.call_count >= 1
        for call_obj in mock_heartbeat.call_args_list:
            payload = call_obj[0][0]
            assert payload[HEARTBEAT_STOP_MONITOR] is True
            assert payload[HEARTBEAT_PARTIAL_OUTPUT_KEY] is None

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_transient_error_heartbeat_includes_partial_output(
        self,
        mock_heartbeat: MagicMock,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test heartbeat on transient poll error also includes STOP_MONITOR and partial_output."""
        transient_error = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(503),
        )
        successful_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={
                "id": 42,
                "status": "successful",
                "artifacts": {},
                "created": "",
                "started": "",
                "finished": "",
            },
        )

        partial_output: dict[str, Any] = {
            "job_id": 42,
            "job_url": "https://aap.example.com/execution/jobs/playbook/42/output",
        }

        start_time = 1000.0
        time_counter = {"value": start_time}

        def mock_time() -> float:
            current = time_counter["value"]
            time_counter["value"] += 1.0
            return current

        with (
            override_settings(
                aap_base_url="https://aap.example.com",
                aap_poll_interval_seconds=0.01,
                aap_timeout_seconds=30,
                aap_token=SecretStr("tok"),
                aap_username=None,
                aap_password=None,
            ),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("time.time", side_effect=mock_time),
        ):
            mock_get.side_effect = [transient_error, successful_response]

            from syntara.core.config.base import get_settings

            settings = get_settings()

            await poll_until_complete(
                client=httpx.AsyncClient(),
                settings=settings,
                job_id=42,
                auth_headers={"Authorization": "Bearer tok"},
                basic_auth=None,
                base_url="https://aap.example.com",
                timeout_seconds=30,
                start_time=start_time,
                job_type="jobs",
                terminal_statuses={"successful", "failed", "error", "canceled"},
                error_class=AAPActivityExecutionError,
                partial_output=partial_output,
            )

        # First heartbeat is from the transient error path
        first_payload = mock_heartbeat.call_args_list[0][0][0]
        assert first_payload[HEARTBEAT_STOP_MONITOR] is True
        assert first_payload[HEARTBEAT_PARTIAL_OUTPUT_KEY] == partial_output

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_500_during_poll_is_retried_and_recovers(
        self,
        mock_heartbeat: MagicMock,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that HTTP 500 during polling is retried and recovers on next cycle."""
        transient_500 = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(500),
        )
        successful_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={
                "id": 42,
                "status": "successful",
                "artifacts": {},
                "created": "",
                "started": "",
                "finished": "",
            },
        )

        start_time = 1000.0
        time_counter = {"value": start_time}

        def mock_time() -> float:
            current = time_counter["value"]
            time_counter["value"] += 1.0
            return current

        with (
            override_settings(
                aap_base_url="https://aap.example.com",
                aap_poll_interval_seconds=0.01,
                aap_timeout_seconds=30,
                aap_token=SecretStr("tok"),
                aap_username=None,
                aap_password=None,
            ),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("time.time", side_effect=mock_time),
        ):
            mock_get.side_effect = [transient_500, successful_response]

            from syntara.core.config.base import get_settings

            settings = get_settings()

            result = await poll_until_complete(
                client=httpx.AsyncClient(),
                settings=settings,
                job_id=42,
                auth_headers={"Authorization": "Bearer tok"},
                basic_auth=None,
                base_url="https://aap.example.com",
                timeout_seconds=30,
                start_time=start_time,
                job_type="jobs",
                terminal_statuses={"successful", "failed", "error", "canceled"},
                error_class=AAPActivityExecutionError,
                partial_output={"job_id": 42, "job_url": "https://aap.example.com/jobs/42"},
            )

        assert result["status"] == "successful"
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_consecutive_poll_errors_triggers_early_failure(
        self,
        mock_heartbeat: MagicMock,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that MAX_CONSECUTIVE_POLL_ERRORS consecutive failures triggers early exit."""
        transient_500 = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(500),
        )

        start_time = 1000.0
        time_counter = {"value": start_time}

        def mock_time() -> float:
            current = time_counter["value"]
            time_counter["value"] += 1.0
            return current

        with (
            override_settings(
                aap_base_url="https://aap.example.com",
                aap_poll_interval_seconds=0.01,
                aap_timeout_seconds=3600,
                aap_token=SecretStr("tok"),
                aap_username=None,
                aap_password=None,
            ),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("time.time", side_effect=mock_time),
        ):
            mock_get.side_effect = [transient_500] * (MAX_CONSECUTIVE_POLL_ERRORS + 1)

            from syntara.core.config.base import get_settings

            settings = get_settings()
            client = httpx.AsyncClient()

            with pytest.raises(AAPActivityExecutionError, match="launched successfully but unable to determine"):
                await poll_until_complete(
                    client=client,
                    settings=settings,
                    job_id=42,
                    auth_headers={"Authorization": "Bearer tok"},
                    basic_auth=None,
                    base_url="https://aap.example.com",
                    timeout_seconds=3600,
                    start_time=start_time,
                    job_type="jobs",
                    terminal_statuses={"successful", "failed", "error", "canceled"},
                    error_class=AAPActivityExecutionError,
                    partial_output={"job_id": 42, "job_url": "https://aap.example.com/jobs/42"},
                )

        assert mock_get.call_count == MAX_CONSECUTIVE_POLL_ERRORS

    @pytest.mark.asyncio
    @patch("temporalio.activity.is_cancelled", return_value=False)
    @patch("temporalio.activity.heartbeat")
    async def test_successful_poll_resets_consecutive_error_counter(
        self,
        mock_heartbeat: MagicMock,
        mock_is_cancelled: object,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that a successful poll resets the consecutive error counter."""
        transient_500 = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(500),
        )
        running_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={"id": 42, "status": "running"},
        )
        successful_response = httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={
                "id": 42,
                "status": "successful",
                "artifacts": {},
                "created": "",
                "started": "",
                "finished": "",
            },
        )

        # Sequence: (N-1) errors → success → (N-1) errors → success
        # Should NOT trigger the cap because a success resets the counter.
        near_cap = MAX_CONSECUTIVE_POLL_ERRORS - 1
        responses: list[Any] = (
            [transient_500] * near_cap + [running_response] + [transient_500] * near_cap + [successful_response]
        )

        start_time = 1000.0
        time_counter = {"value": start_time}

        def mock_time() -> float:
            current = time_counter["value"]
            time_counter["value"] += 1.0
            return current

        with (
            override_settings(
                aap_base_url="https://aap.example.com",
                aap_poll_interval_seconds=0.01,
                aap_timeout_seconds=3600,
                aap_token=SecretStr("tok"),
                aap_username=None,
                aap_password=None,
            ),
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            patch("time.time", side_effect=mock_time),
        ):
            mock_get.side_effect = responses

            from syntara.core.config.base import get_settings

            settings = get_settings()

            result = await poll_until_complete(
                client=httpx.AsyncClient(),
                settings=settings,
                job_id=42,
                auth_headers={"Authorization": "Bearer tok"},
                basic_auth=None,
                base_url="https://aap.example.com",
                timeout_seconds=3600,
                start_time=start_time,
                job_type="jobs",
                terminal_statuses={"successful", "failed", "error", "canceled"},
                error_class=AAPActivityExecutionError,
                partial_output={"job_id": 42, "job_url": "https://aap.example.com/jobs/42"},
            )

        assert result["status"] == "successful"
        assert mock_get.call_count == len(responses)
