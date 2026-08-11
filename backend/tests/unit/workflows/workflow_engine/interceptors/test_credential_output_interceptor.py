"""Tests for CredentialOutputInterceptor."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.interceptors.credential_output_interceptor import (
    _CredentialOutputActivityInterceptor,
    _input_has_credentials,
)


class TestInputHasCredentials:
    """Tests for _input_has_credentials helper."""

    def test_detects_credentials_in_first_arg(self) -> None:
        args = [{"url": "http://example.com", "_resolved_credentials": {"extra_vars": {}}}]
        assert _input_has_credentials(args) is True

    def test_returns_false_without_credentials(self) -> None:
        args = [{"url": "http://example.com"}]
        assert _input_has_credentials(args) is False

    def test_returns_false_for_empty_args(self) -> None:
        assert _input_has_credentials([]) is False

    def test_returns_false_for_non_dict_first_arg(self) -> None:
        args = ["not-a-dict"]
        assert _input_has_credentials(args) is False


class TestCredentialOutputActivityInterceptor:
    """Tests for the activity interceptor."""

    @pytest.fixture
    def next_interceptor(self) -> MagicMock:
        mock = MagicMock()
        mock.execute_activity = AsyncMock()
        return mock

    @pytest.fixture
    def interceptor(self, next_interceptor: MagicMock) -> _CredentialOutputActivityInterceptor:
        return _CredentialOutputActivityInterceptor(next_interceptor)

    def _make_input(self, *, has_credentials: bool) -> MagicMock:
        mock_input = MagicMock()
        if has_credentials:
            mock_input.args = [{"url": "http://x.com", "_resolved_credentials": {"extra_vars": {}}}]
        else:
            mock_input.args = [{"url": "http://x.com"}]
        return mock_input

    @pytest.mark.asyncio
    async def test_marks_result_when_input_has_credentials(
        self, interceptor: _CredentialOutputActivityInterceptor, next_interceptor: MagicMock
    ) -> None:
        next_interceptor.execute_activity.return_value = {"output": {"stdout": "secret"}}
        result = await interceptor.execute_activity(self._make_input(has_credentials=True))
        assert result["_has_credentials"] is True
        assert result["output"]["stdout"] == "secret"

    @pytest.mark.asyncio
    async def test_does_not_mark_result_without_credentials(
        self, interceptor: _CredentialOutputActivityInterceptor, next_interceptor: MagicMock
    ) -> None:
        next_interceptor.execute_activity.return_value = {"output": {"stdout": "safe"}}
        result = await interceptor.execute_activity(self._make_input(has_credentials=False))
        assert "_has_credentials" not in result

    @pytest.mark.asyncio
    async def test_marks_error_details_when_input_has_credentials(
        self, interceptor: _CredentialOutputActivityInterceptor, next_interceptor: MagicMock
    ) -> None:
        error_detail = {"output": {"body": "echoed-secret"}}
        next_interceptor.execute_activity.side_effect = ApplicationError(
            "HTTP 500", error_detail, type="HTTPError", non_retryable=True
        )
        with pytest.raises(ApplicationError) as exc_info:
            await interceptor.execute_activity(self._make_input(has_credentials=True))
        assert exc_info.value.details[0]["_has_credentials"] is True

    @pytest.mark.asyncio
    async def test_does_not_mark_error_details_without_credentials(
        self, interceptor: _CredentialOutputActivityInterceptor, next_interceptor: MagicMock
    ) -> None:
        error_detail = {"output": {"body": "error"}}
        next_interceptor.execute_activity.side_effect = ApplicationError(
            "HTTP 500", error_detail, type="HTTPError", non_retryable=True
        )
        with pytest.raises(ApplicationError) as exc_info:
            await interceptor.execute_activity(self._make_input(has_credentials=False))
        assert "_has_credentials" not in exc_info.value.details[0]

    @pytest.mark.asyncio
    async def test_passes_through_non_dict_result(
        self, interceptor: _CredentialOutputActivityInterceptor, next_interceptor: MagicMock
    ) -> None:
        next_interceptor.execute_activity.return_value = "string-result"
        result = await interceptor.execute_activity(self._make_input(has_credentials=True))
        assert result == "string-result"

    @pytest.mark.asyncio
    async def test_propagates_non_application_errors(
        self, interceptor: _CredentialOutputActivityInterceptor, next_interceptor: MagicMock
    ) -> None:
        next_interceptor.execute_activity.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            await interceptor.execute_activity(self._make_input(has_credentials=True))
