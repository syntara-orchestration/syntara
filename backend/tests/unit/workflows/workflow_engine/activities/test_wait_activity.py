"""Tests for wait activity and complete_wait activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode

from syntara.workflows.workflow_engine.activities.wait_activity import complete_wait, wait
from tests.fixtures.temporal import CompleteAsyncError

SETTINGS_PATH = "syntara.workflows.workflow_engine.activities.wait_activity.get_runtime_settings"


def _mock_settings(max_wait_seconds: int = 2592000) -> MagicMock:
    """Create a mock settings cache that returns the given max wait."""
    mock_cache = MagicMock()
    mock_cache.get_int = AsyncMock(return_value=max_wait_seconds)
    return MagicMock(return_value=mock_cache)


class TestWaitValidDuration:
    """Valid duration configs raise CompleteAsyncError (async completion)."""

    @pytest.mark.asyncio
    async def test_valid_seconds(self) -> None:
        with patch(SETTINGS_PATH, _mock_settings()), pytest.raises(CompleteAsyncError):
            await wait({"duration": 5400}, None)

    @pytest.mark.asyncio
    async def test_one_second(self) -> None:
        with patch(SETTINGS_PATH, _mock_settings()), pytest.raises(CompleteAsyncError):
            await wait({"duration": 1}, None)

    @pytest.mark.asyncio
    async def test_large_duration(self) -> None:
        with patch(SETTINGS_PATH, _mock_settings(max_wait_seconds=2592000)), pytest.raises(CompleteAsyncError):
            await wait({"duration": 2592000}, None)


class TestWaitZeroDuration:
    """Zero total duration raises ApplicationError."""

    @pytest.mark.asyncio
    async def test_zero_seconds_raises_application_error(self) -> None:
        with pytest.raises(ApplicationError, match="greater than zero") as exc_info:
            await wait({"duration": 0}, None)
        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_missing_seconds_raises_application_error(self) -> None:
        with pytest.raises(ApplicationError, match="greater than zero"):
            await wait({}, None)


class TestWaitNegativeValues:
    """Negative values raise ApplicationError."""

    @pytest.mark.asyncio
    async def test_negative_seconds(self) -> None:
        with pytest.raises(ApplicationError, match="greater than zero") as exc_info:
            await wait({"duration": -10}, None)
        assert exc_info.value.type == "ConfigError"


class TestWaitInvalidTypes:
    """Non-integer values raise ApplicationError."""

    @pytest.mark.asyncio
    async def test_string_value(self) -> None:
        with pytest.raises(ApplicationError, match="positive integer"):
            await wait({"duration": "thirty"}, None)

    @pytest.mark.asyncio
    async def test_float_value(self) -> None:
        with pytest.raises(ApplicationError, match="positive integer"):
            await wait({"duration": 1.5}, None)

    @pytest.mark.asyncio
    async def test_none_value(self) -> None:
        with pytest.raises(ApplicationError, match="positive integer"):
            await wait({"duration": None}, None)


class TestWaitBoolValues:
    """Boolean values are rejected (bool is subclass of int in Python)."""

    @pytest.mark.asyncio
    async def test_bool_true_rejected(self) -> None:
        with pytest.raises(ApplicationError, match="positive integer"):
            await wait({"duration": True}, None)

    @pytest.mark.asyncio
    async def test_bool_false_rejected(self) -> None:
        with pytest.raises(ApplicationError, match="positive integer"):
            await wait({"duration": False}, None)


class TestWaitGlobalMaxDuration:
    """Total duration is checked against the global settings max."""

    @pytest.mark.asyncio
    async def test_exceeds_global_max(self) -> None:
        with (
            patch(SETTINGS_PATH, _mock_settings(max_wait_seconds=3600)),
            pytest.raises(ApplicationError, match="exceeds maximum allowed") as exc_info,
        ):
            await wait({"duration": 86400}, None)
        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_at_global_max_is_valid(self) -> None:
        with patch(SETTINGS_PATH, _mock_settings(max_wait_seconds=3600)), pytest.raises(CompleteAsyncError):
            await wait({"duration": 3600}, None)

    @pytest.mark.asyncio
    async def test_below_global_max_is_valid(self) -> None:
        with patch(SETTINGS_PATH, _mock_settings(max_wait_seconds=86400)), pytest.raises(CompleteAsyncError):
            await wait({"duration": 3600}, None)

    @pytest.mark.asyncio
    async def test_large_duration_exceeding_global_max(self) -> None:
        with (
            patch(SETTINGS_PATH, _mock_settings(max_wait_seconds=2592000)),
            pytest.raises(ApplicationError, match="exceeds maximum"),
        ):
            await wait({"duration": 2678400}, None)


class TestWaitNonRetryable:
    """All validation errors are non-retryable."""

    @pytest.mark.asyncio
    async def test_config_errors_are_non_retryable(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await wait({"duration": -1}, None)
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_zero_duration_is_non_retryable(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await wait({"duration": 0}, None)
        assert exc_info.value.non_retryable is True


class TestCompleteWaitHappyPath:
    """complete_wait successfully completes the async activity."""

    @pytest.mark.asyncio
    async def test_completes_activity_via_handle(self) -> None:
        mock_handle = AsyncMock()
        mock_client = MagicMock()
        mock_client.get_async_activity_handle.return_value = mock_handle

        mock_service = MagicMock()
        mock_service.temporal_client = mock_client

        with patch(
            "syntara.workflows.workflow_engine.activities.wait_activity.get_activity_sync_service",
            return_value=mock_service,
        ):
            result = await complete_wait("wf-123", "run-456", "node-wait-1")

        assert result == {"output": {"status": "completed"}}
        mock_client.get_async_activity_handle.assert_called_once_with(
            workflow_id="wf-123",
            run_id="run-456",
            activity_id="node-wait-1",
        )
        mock_handle.complete.assert_called_once_with({"output": {"status": "completed"}})


class TestCompleteWaitIdempotent:
    """complete_wait handles already-completed activities gracefully."""

    @pytest.mark.asyncio
    async def test_already_completed_is_swallowed(self) -> None:
        mock_handle = AsyncMock()
        mock_handle.complete.side_effect = RPCError(
            "activity already completed",
            RPCStatusCode.NOT_FOUND,
            b"",
        )
        mock_client = MagicMock()
        mock_client.get_async_activity_handle.return_value = mock_handle

        mock_service = MagicMock()
        mock_service.temporal_client = mock_client

        with patch(
            "syntara.workflows.workflow_engine.activities.wait_activity.get_activity_sync_service",
            return_value=mock_service,
        ):
            result = await complete_wait("wf-123", "run-456", "node-wait-1")

        assert result == {"output": {"status": "completed"}}

    @pytest.mark.asyncio
    async def test_not_found_is_swallowed(self) -> None:
        mock_handle = AsyncMock()
        mock_handle.complete.side_effect = RPCError(
            "activity not found",
            RPCStatusCode.NOT_FOUND,
            b"",
        )
        mock_client = MagicMock()
        mock_client.get_async_activity_handle.return_value = mock_handle

        mock_service = MagicMock()
        mock_service.temporal_client = mock_client

        with patch(
            "syntara.workflows.workflow_engine.activities.wait_activity.get_activity_sync_service",
            return_value=mock_service,
        ):
            result = await complete_wait("wf-123", "run-456", "node-wait-1")

        assert result == {"output": {"status": "completed"}}


class TestCompleteWaitUnexpectedError:
    """complete_wait re-raises unexpected RPCErrors."""

    @pytest.mark.asyncio
    async def test_unexpected_rpc_error_propagates(self) -> None:
        mock_handle = AsyncMock()
        mock_handle.complete.side_effect = RPCError(
            "internal server error",
            RPCStatusCode.INTERNAL,
            b"",
        )
        mock_client = MagicMock()
        mock_client.get_async_activity_handle.return_value = mock_handle

        mock_service = MagicMock()
        mock_service.temporal_client = mock_client

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.wait_activity.get_activity_sync_service",
                return_value=mock_service,
            ),
            pytest.raises(RPCError, match="internal server error"),
        ):
            await complete_wait("wf-123", "run-456", "node-wait-1")


class TestCompleteWaitServiceUnavailable:
    """complete_wait raises when sync service is unavailable."""

    @pytest.mark.asyncio
    async def test_raises_when_service_is_none(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.wait_activity.get_activity_sync_service",
                return_value=None,
            ),
            pytest.raises(ApplicationError, match="sync service not available"),
        ):
            await complete_wait("wf-123", "run-456", "node-wait-1")
