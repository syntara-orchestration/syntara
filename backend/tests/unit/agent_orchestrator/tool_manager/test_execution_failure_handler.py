"""Unit tests for tool execution failure handler."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolCallRequest, ToolInvocationError
from langgraph.types import Command
from pydantic import BaseModel, ValidationError

from syntara.agent_orchestrator.tool_manager.execution_failure_handler import (
    _resolve_execution_status,
    _should_auto_disable_tool,
    create_tool_awrapper,
    create_tool_wrapper,
)
from syntara.core.utils.retry import is_retryable_error
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus


async def _execute_async_wrapper(
    tool_name: str,
    tool_call_id: str,
    exception: Exception | None,
    tool: BaseTool | None,
    success_content: str | None = None,
) -> ToolMessage | Command[Any]:
    """Helper function to execute async tool wrapper with configurable success/failure scenarios.

    Args:
        tool_name: Name of the tool being tested
        tool_call_id: ID for the tool call
        exception: Exception to raise in mock_execute (None for success case)
        tool: BaseTool instance (or None for missing tool tests)
        success_content: Content to return for success case (ignored if exception is provided)

    Returns:
        The ToolMessage or Command result from the async wrapper execution

    """
    wrapper = create_tool_awrapper(session_id="session-abc", invocation_id=uuid4(), execution_id=uuid4())

    async def mock_execute(tool_request: ToolCallRequest) -> ToolMessage | Command[Any]:
        if exception is not None:
            raise exception

        # Success case
        return ToolMessage(
            content=success_content or "Success!",
            tool_call_id=tool_call_id,
            name=tool_name,
        )

    tool_call = ToolCall(name=tool_name, args={}, id=tool_call_id)
    request = ToolCallRequest(
        tool_call=tool_call,
        tool=tool,
        state={},
        runtime=Mock() if tool is not None else None,  # type: ignore
    )

    return await wrapper(request, mock_execute)


def _execute_sync_wrapper(
    tool_name: str,
    tool_call_id: str,
    exception: Exception | None,
    tool: BaseTool | None,
    success_content: str | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> ToolMessage | Command[Any]:
    """Helper function to execute sync tool wrapper with configurable success/failure scenarios.

    Args:
        tool_name: Name of the tool being tested
        tool_call_id: ID for the tool call
        exception: Exception to raise in mock_execute (None for success case)
        tool: BaseTool instance (or None for missing tool tests)
        success_content: Content to return for success case (ignored if exception is provided)
        loop: Optional event loop to pass to create_tool_wrapper

    Returns:
        The ToolMessage result from the sync wrapper execution

    """
    wrapper = create_tool_wrapper(session_id="session-abc", invocation_id=uuid4(), execution_id=uuid4(), loop=loop)

    def mock_execute(tool_request: ToolCallRequest) -> ToolMessage | Command[Any]:
        if exception is not None:
            raise exception

        # Success case
        return ToolMessage(
            content=success_content or "Success!",
            tool_call_id=tool_call_id,
            name=tool_name,
        )

    tool_call = ToolCall(name=tool_name, args={}, id=tool_call_id)
    request = ToolCallRequest(
        tool_call=tool_call,
        tool=tool,
        state={},
        runtime=Mock() if tool is not None else None,  # type: ignore
    )

    return wrapper(request, mock_execute)


class MockTool(BaseTool):
    """Mock tool for testing."""

    name: str = "test_tool"
    description: str = "Test tool for unit tests"

    def _run(self, *args: Any, **kwargs: Any) -> str:  # noqa: ANN401
        """Mock run method."""
        return "test result"


class TestAsyncToolWrapper:
    """Test async tool wrapper functionality."""

    async def test_async_tool_wrapper_success(self) -> None:
        """Test async tool wrapper when execution succeeds."""
        result = await _execute_async_wrapper(
            tool_name="test_tool",
            tool_call_id="test-id",
            exception=None,
            tool=MockTool(),
            success_content="Success!",
        )

        # Should return the successful result
        assert isinstance(result, ToolMessage)
        assert result.content == "Success!"

    async def test_async_tool_wrapper_failure(self) -> None:
        """Test async tool wrapper when execution fails."""
        result = await _execute_async_wrapper(
            tool_name="test_tool",
            tool_call_id="test-id",
            exception=ValueError("Test failure"),
            tool=MockTool(),
        )

        # Should return error ToolMessage
        assert isinstance(result, ToolMessage)
        assert "Tool execution failed: ValueError: Test failure" in result.content
        assert result.tool_call_id == "test-id"
        assert result.name == "test_tool"
        assert result.status == "error"


class TestSyncToolWrapper:
    """Test synchronous tool wrapper functionality."""

    def test_sync_tool_wrapper_success(self) -> None:
        """Test sync tool wrapper when execution succeeds."""
        result = _execute_sync_wrapper(
            tool_name="test_tool",
            tool_call_id="test-id",
            exception=None,
            tool=MockTool(),
            success_content="Success!",
        )

        # Should return the successful result
        assert isinstance(result, ToolMessage)
        assert result.content == "Success!"

    @pytest.mark.usefixtures("fast_retry_settings")
    def test_sync_tool_wrapper_failure(self) -> None:
        """Test sync tool wrapper when execution fails."""
        result = _execute_sync_wrapper(
            tool_name="test_tool",
            tool_call_id="test-id",
            exception=ValueError("Test failure"),
            tool=MockTool(),
        )

        # Should return error ToolMessage
        assert isinstance(result, ToolMessage)
        assert "Tool execution failed: ValueError: Test failure" in result.content
        assert result.tool_call_id == "test-id"
        assert result.name == "test_tool"
        assert result.status == "error"

    @pytest.mark.usefixtures("fast_retry_settings")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    def test_sync_wrapper_tool_disable_scheduling(self, mock_logger: Mock, mock_disable_tool: AsyncMock) -> None:
        """Test sync tool wrapper disables tool for valid tool_id (no event loop provided)."""
        # Create BaseTool with valid tool_id
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "sync_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = _execute_sync_wrapper(
            tool_name="sync_tool",
            tool_call_id="sync-call-123",
            exception=RuntimeError("Sync failure"),
            tool=tool,
        )

        # Verify logging
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="sync_tool",
        )

        # Verify _disable_tool_by_id was actually called (fallback path using asyncio.run)
        mock_disable_tool.assert_called_once()
        args = mock_disable_tool.call_args[0]
        assert len(args) == 2
        disabled_tool_id, disabled_error = args
        assert disabled_tool_id == valid_tool_id
        assert isinstance(disabled_error, RuntimeError)
        assert str(disabled_error) == "Sync failure"

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: RuntimeError: Sync failure"
        assert result.tool_call_id == "sync-call-123"
        assert result.name == "sync_tool"
        assert result.status == "error"

    @pytest.mark.usefixtures("fast_retry_settings")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    def test_sync_wrapper_tool_disable_with_event_loop(self, mock_logger: Mock, mock_disable_tool: AsyncMock) -> None:
        """Test sync tool wrapper disables tool for valid tool_id (with event loop provided)."""
        # Create a mock event loop
        import asyncio

        mock_loop = Mock(spec=asyncio.AbstractEventLoop)

        # Create BaseTool with valid tool_id
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "loop_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = _execute_sync_wrapper(
            tool_name="loop_tool",
            tool_call_id="loop-call-456",
            exception=ConnectionError("Network failure"),
            tool=tool,
            loop=mock_loop,
        )

        # Verify logging
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="loop_tool",
        )

        # Verify _disable_tool_by_id was actually called (via run_coroutine_threadsafe path)
        mock_disable_tool.assert_called_once()
        args = mock_disable_tool.call_args[0]
        assert len(args) == 2
        disabled_tool_id, disabled_error = args
        assert disabled_tool_id == valid_tool_id
        assert isinstance(disabled_error, ConnectionError)
        assert str(disabled_error) == "Network failure"

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: ConnectionError: Network failure"
        assert result.tool_call_id == "loop-call-456"
        assert result.name == "loop_tool"
        assert result.status == "error"


class TestRetryableErrorIntegration:
    """Test integration with is_retryable_error function."""

    @pytest.mark.asyncio
    async def test_retryable_error_in_handler_context(
        self,
    ) -> None:
        """Test retryable error classification in handler context."""
        # Test error classification - use only errors that are actually retryable
        retryable_errors: list[Exception] = [
            TimeoutError("Async timeout"),
        ]

        non_retryable_errors = [
            ValueError("Invalid parameter"),
            KeyError("Missing key"),
            AttributeError("Missing attribute"),
            ConnectionError("Network failure"),  # Not retryable in the current implementation
        ]

        for error in retryable_errors:
            assert is_retryable_error(error), f"{error} should be retryable"

        for error in non_retryable_errors:
            assert not is_retryable_error(error), f"{error} should not be retryable"


class TestToolWrapperFailureScenarios:
    """Test comprehensive failure scenarios for tool wrapper."""

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_tool_wrapper_missing_base_tool(self, mock_logger: Mock) -> None:
        """Test tool wrapper when BaseTool is None."""
        result = await _execute_async_wrapper(
            tool_name="test_tool",
            tool_call_id="test-call-id",
            exception=RuntimeError("Tool execution failed"),
            tool=None,  # Missing BaseTool
        )

        # Verify error logging
        assert mock_logger.exception.call_count == 1
        assert mock_logger.error.call_count == 1
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="test_tool",
        )
        mock_logger.error.assert_called_once_with(
            "BaseTool missing metadata - this indicates a bug in tool synchronization", tool_name="test_tool"
        )

        # Verify error ToolMessage returned
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: RuntimeError: Tool execution failed"
        assert result.tool_call_id == "test-call-id"
        assert result.name == "test_tool"
        assert result.status == "error"

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_tool_wrapper_missing_metadata_attribute(self, mock_logger: Mock) -> None:
        """Test tool wrapper when BaseTool has no metadata attribute."""
        # Create BaseTool without metadata attribute
        tool = Mock(spec=BaseTool)
        tool.name = "network_tool"
        # Deliberately don't set metadata attribute

        result = await _execute_async_wrapper(
            tool_name="network_tool",
            tool_call_id="network-call-123",
            exception=ConnectionError("Network timeout"),
            tool=tool,
        )

        # Verify logging
        assert mock_logger.exception.call_count == 1
        assert mock_logger.error.call_count == 1
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="network_tool",
        )
        mock_logger.error.assert_called_once_with(
            "BaseTool missing metadata - this indicates a bug in tool synchronization", tool_name="network_tool"
        )

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: ConnectionError: Network timeout"
        assert result.tool_call_id == "network-call-123"
        assert result.name == "network_tool"
        assert result.status == "error"

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_tool_wrapper_non_dict_metadata(self, mock_logger: Mock) -> None:
        """Test tool wrapper when BaseTool metadata is not a dictionary."""
        # Create BaseTool with non-dict metadata
        tool = Mock(spec=BaseTool)
        tool.name = "config_tool"
        tool.metadata = "invalid_metadata_string"  # Should be dict, not string

        result = await _execute_async_wrapper(
            tool_name="config_tool",
            tool_call_id="config-call-456",
            exception=ValueError("Invalid configuration"),
            tool=tool,
        )

        # Verify logging
        assert mock_logger.exception.call_count == 1
        assert mock_logger.error.call_count == 1
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="config_tool",
        )
        mock_logger.error.assert_called_once_with(
            "BaseTool missing metadata - this indicates a bug in tool synchronization", tool_name="config_tool"
        )

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: ValueError: Invalid configuration"
        assert result.tool_call_id == "config-call-456"
        assert result.name == "config_tool"
        assert result.status == "error"

    @pytest.mark.usefixtures("fast_retry_settings")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_tool_wrapper_missing_tool_id_in_metadata(self, mock_logger: Mock) -> None:
        """Test tool wrapper when metadata exists but tool_id is missing."""
        # Create BaseTool with metadata but no tool_id
        tool = Mock(spec=BaseTool)
        tool.name = "timeout_tool"
        tool.metadata = {"some_other_field": "value"}  # Missing tool_id

        result = await _execute_async_wrapper(
            tool_name="timeout_tool",
            tool_call_id="timeout-call-789",
            exception=TimeoutError("Request timeout"),
            tool=tool,
        )

        # Verify logging
        assert mock_logger.exception.call_count == 1
        assert mock_logger.error.call_count == 1
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="timeout_tool",
        )
        mock_logger.error.assert_called_once_with(
            "BaseTool metadata missing tool_id - this indicates a bug in tool synchronization",
            tool_name="timeout_tool",
        )

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: TimeoutError: Request timeout"
        assert result.tool_call_id == "timeout-call-789"
        assert result.name == "timeout_tool"
        assert result.status == "error"

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_tool_wrapper_invalid_tool_id_format(self, mock_logger: Mock) -> None:
        """Test tool wrapper when tool_id in metadata is not a valid UUID."""
        # Create BaseTool with invalid tool_id format
        tool = Mock(spec=BaseTool)
        tool.name = "key_tool"
        tool.metadata = {"tool_id": "invalid-uuid-format"}  # Invalid UUID

        result = await _execute_async_wrapper(
            tool_name="key_tool",
            tool_call_id="key-call-abc",
            exception=KeyError("Missing required key"),
            tool=tool,
        )

        # Verify logging
        assert mock_logger.exception.call_count == 2
        mock_logger.exception.assert_any_call(
            "Tool execution failed during wrapped call",
            tool_name="key_tool",
        )
        mock_logger.exception.assert_any_call(
            "Invalid tool_id format in metadata - this indicates a bug in tool synchronization",
            tool_id_value="invalid-uuid-format",
            tool_name="key_tool",
        )

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: KeyError: 'Missing required key'"
        assert result.tool_call_id == "key-call-abc"
        assert result.name == "key_tool"
        assert result.status == "error"

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_tool_wrapper_successful_tool_id_extraction_and_disable_scheduling(
        self, mock_logger: Mock, mock_disable_tool: AsyncMock
    ) -> None:
        """Test tool wrapper with valid tool_id that gets disabled directly."""
        # Create BaseTool with valid tool_id
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "disk_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = await _execute_async_wrapper(
            tool_name="disk_tool",
            tool_call_id="disk-call-def",
            exception=OSError("Disk full"),
            tool=tool,
        )

        # Verify logging
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="disk_tool",
        )
        mock_logger.debug.assert_any_call("Extracted tool_id from metadata", tool_id=valid_tool_id)

        # Verify tool disable was called directly
        mock_disable_tool.assert_called_once()
        args, _kwargs = mock_disable_tool.call_args
        assert len(args) == 2
        disabled_tool_id, disabled_error = args
        assert disabled_tool_id == valid_tool_id
        assert isinstance(disabled_error, OSError)
        assert str(disabled_error) == "Disk full"

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: OSError: Disk full"
        assert result.tool_call_id == "disk-call-def"
        assert result.name == "disk_tool"
        assert result.status == "error"

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_tool_wrapper_none_tool_id_in_metadata(self, mock_logger: Mock) -> None:
        """Test tool wrapper when tool_id is explicitly None in metadata."""
        # Create BaseTool with None tool_id
        tool = Mock(spec=BaseTool)
        tool.name = "attr_tool"
        tool.metadata = {"tool_id": None}  # Explicitly None

        result = await _execute_async_wrapper(
            tool_name="attr_tool",
            tool_call_id="attr-call-ghi",
            exception=AttributeError("Missing attribute"),
            tool=tool,
        )

        # Verify logging
        assert mock_logger.exception.call_count == 1
        assert mock_logger.error.call_count == 1
        mock_logger.exception.assert_called_once_with(
            "Tool execution failed during wrapped call",
            tool_name="attr_tool",
        )
        mock_logger.error.assert_called_once_with(
            "BaseTool metadata missing tool_id - this indicates a bug in tool synchronization",
            tool_name="attr_tool",
        )

        # Verify response
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool execution failed: AttributeError: Missing attribute"
        assert result.tool_call_id == "attr-call-ghi"
        assert result.name == "attr_tool"
        assert result.status == "error"


class TestResolveToolExecutionStatus:
    """Test _resolve_execution_status maps exceptions to correct ToolExecutionStatus."""

    def test_none_maps_to_success(self) -> None:
        assert _resolve_execution_status(None) == ToolExecutionStatus.SUCCESS

    def test_timeout_error_maps_to_timeout(self) -> None:
        assert _resolve_execution_status(TimeoutError("timed out")) == ToolExecutionStatus.TIMEOUT

    def test_asyncio_timeout_error_maps_to_timeout(self) -> None:
        assert _resolve_execution_status(TimeoutError()) == ToolExecutionStatus.TIMEOUT

    def test_value_error_maps_to_error(self) -> None:
        assert _resolve_execution_status(ValueError("bad value")) == ToolExecutionStatus.ERROR

    def test_runtime_error_maps_to_error(self) -> None:
        assert _resolve_execution_status(RuntimeError("runtime")) == ToolExecutionStatus.ERROR

    def test_connection_error_maps_to_error(self) -> None:
        assert _resolve_execution_status(ConnectionError("conn")) == ToolExecutionStatus.ERROR


class TestShouldAutoDisableTool:
    """Test failure classification for shared-tool auto-disable."""

    def test_validation_error_does_not_auto_disable(self) -> None:
        class _Args(BaseModel):
            count: int

        with pytest.raises(ValidationError) as exc_info:
            _Args.model_validate({"count": "not-an-int"})

        assert _should_auto_disable_tool(exc_info.value) is False

    def test_tool_invocation_error_does_not_auto_disable(self) -> None:
        """LangGraph wraps schema ValidationError as ToolInvocationError."""

        class _Args(BaseModel):
            count: int

        with pytest.raises(ValidationError) as exc_info:
            _Args.model_validate({"count": "not-an-int"})

        wrapped = ToolInvocationError("echo_count", exc_info.value, {"count": "not-an-int"})
        assert _should_auto_disable_tool(wrapped) is False

    def test_wrapped_validation_error_cause_does_not_auto_disable(self) -> None:
        """Generic wrappers that set __cause__ to ValidationError are non-outage."""

        class _Args(BaseModel):
            count: int

        with pytest.raises(ValidationError) as exc_info:
            _Args.model_validate({"count": "not-an-int"})

        wrapped = RuntimeError("tool call failed")
        wrapped.__cause__ = exc_info.value
        assert _should_auto_disable_tool(wrapped) is False

    @pytest.mark.parametrize(
        "error",
        [
            ValueError("Invalid parameter"),
            TypeError("bad type"),
            KeyError("missing_arg"),
            AttributeError("missing attribute"),
        ],
    )
    def test_caller_argument_errors_do_not_auto_disable(self, error: Exception) -> None:
        assert _should_auto_disable_tool(error) is False

    @pytest.mark.parametrize(
        "error",
        [
            TimeoutError("Request timed out"),
            ConnectionError("Network failure"),
            OSError("Disk full"),
            RuntimeError("Provider unavailable"),
        ],
    )
    def test_outage_errors_do_auto_disable(self, error: Exception) -> None:
        assert _should_auto_disable_tool(error) is True


class TestAutoDisableClassificationInWrappers:
    """Test wrappers only auto-disable on outage failures."""

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_async_wrapper_skips_disable_for_validation_error(
        self, mock_logger: Mock, mock_disable_tool: AsyncMock
    ) -> None:
        """Pydantic ValidationError records failure but does not disable the tool."""

        class _Args(BaseModel):
            count: int

        with pytest.raises(ValidationError) as exc_info:
            _Args.model_validate({"count": "not-an-int"})

        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "validated_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = await _execute_async_wrapper(
            tool_name="validated_tool",
            tool_call_id="validation-call-1",
            exception=exc_info.value,
            tool=tool,
        )

        mock_disable_tool.assert_not_called()
        mock_logger.info.assert_any_call(
            "Skipping tool auto-disable for non-outage failure",
            tool_id=valid_tool_id,
            error_type="ValidationError",
        )
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "ValidationError" in result.content

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_async_wrapper_skips_disable_for_tool_invocation_error(
        self, mock_logger: Mock, mock_disable_tool: AsyncMock
    ) -> None:
        """LangGraph ToolInvocationError (schema fault) must not disable the shared tool."""

        class _Args(BaseModel):
            count: int

        with pytest.raises(ValidationError) as exc_info:
            _Args.model_validate({"count": "not-an-int"})

        invocation_error = ToolInvocationError(
            "schema_tool",
            exc_info.value,
            {"count": "not-an-int"},
        )
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "schema_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = await _execute_async_wrapper(
            tool_name="schema_tool",
            tool_call_id="schema-call-1",
            exception=invocation_error,
            tool=tool,
        )

        mock_disable_tool.assert_not_called()
        mock_logger.info.assert_any_call(
            "Skipping tool auto-disable for non-outage failure",
            tool_id=valid_tool_id,
            error_type="ToolInvocationError",
        )
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "ToolInvocationError" in result.content

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    async def test_async_wrapper_skips_disable_for_value_error(
        self, mock_logger: Mock, mock_disable_tool: AsyncMock
    ) -> None:
        """ValueError from bad args records failure but does not disable the tool."""
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "arg_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = await _execute_async_wrapper(
            tool_name="arg_tool",
            tool_call_id="arg-call-1",
            exception=ValueError("Invalid parameter"),
            tool=tool,
        )

        mock_disable_tool.assert_not_called()
        mock_logger.info.assert_any_call(
            "Skipping tool auto-disable for non-outage failure",
            tool_id=valid_tool_id,
            error_type="ValueError",
        )
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "ValueError: Invalid parameter" in result.content

    @pytest.mark.usefixtures("fast_retry_settings")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler.logger")
    def test_sync_wrapper_skips_disable_for_type_error(self, mock_logger: Mock, mock_disable_tool: AsyncMock) -> None:
        """TypeError from bad args records failure but does not disable the tool."""
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "type_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = _execute_sync_wrapper(
            tool_name="type_tool",
            tool_call_id="type-call-1",
            exception=TypeError("expected str, got int"),
            tool=tool,
        )

        mock_disable_tool.assert_not_called()
        mock_logger.info.assert_any_call(
            "Skipping tool auto-disable for non-outage failure",
            tool_id=valid_tool_id,
            error_type="TypeError",
        )
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "TypeError" in result.content

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    async def test_async_wrapper_disables_on_timeout(self, mock_disable_tool: AsyncMock) -> None:
        """TimeoutError still auto-disables the shared tool."""
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "slow_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = await _execute_async_wrapper(
            tool_name="slow_tool",
            tool_call_id="timeout-call-1",
            exception=TimeoutError("Request timed out"),
            tool=tool,
        )

        mock_disable_tool.assert_called_once()
        disabled_tool_id, disabled_error = mock_disable_tool.call_args[0]
        assert disabled_tool_id == valid_tool_id
        assert isinstance(disabled_error, TimeoutError)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id")
    async def test_async_wrapper_disables_on_connection_error(self, mock_disable_tool: AsyncMock) -> None:
        """ConnectionError (tool/provider outage) still auto-disables the shared tool."""
        valid_tool_id = uuid4()
        tool = Mock(spec=BaseTool)
        tool.name = "remote_tool"
        tool.metadata = {"tool_id": str(valid_tool_id)}

        result = await _execute_async_wrapper(
            tool_name="remote_tool",
            tool_call_id="conn-call-1",
            exception=ConnectionError("Network failure"),
            tool=tool,
        )

        mock_disable_tool.assert_called_once()
        disabled_tool_id, disabled_error = mock_disable_tool.call_args[0]
        assert disabled_tool_id == valid_tool_id
        assert isinstance(disabled_error, ConnectionError)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "ConnectionError" in result.content


class TestMetricsEmissionAndDbPersistence:
    """Test that tool wrappers emit metrics with correct status and persist to DB."""

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._persist_tool_execution_to_db")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._emit_tool_metrics")
    async def test_async_wrapper_success_emits_success_status(self, mock_emit: Mock, mock_persist: AsyncMock) -> None:
        """Test that successful async execution emits SUCCESS status and persists to DB."""
        tool = Mock(spec=BaseTool)
        tool.name = "my_tool"
        tool.metadata = {"tool_id": str(uuid4()), "namespaced_name": "provider::my_tool"}

        await _execute_async_wrapper(
            tool_name="my_tool",
            tool_call_id="call-1",
            exception=None,
            tool=tool,
            success_content="OK",
        )

        mock_emit.assert_called_once()
        _, _, emit_status = mock_emit.call_args[0]
        assert emit_status == ToolExecutionStatus.SUCCESS

        mock_persist.assert_awaited_once()
        persist_args = mock_persist.call_args
        assert persist_args[0][0] is tool
        assert persist_args[0][2] == ToolExecutionStatus.SUCCESS
        assert persist_args[1]["error_message"] is None

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._persist_tool_execution_to_db")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._emit_tool_metrics")
    async def test_async_wrapper_timeout_emits_timeout_status(self, mock_emit: Mock, mock_persist: AsyncMock) -> None:
        """Test that TimeoutError emits TIMEOUT status and persists with error message."""
        tool = Mock(spec=BaseTool)
        tool.name = "slow_tool"
        tool.metadata = {"tool_id": str(uuid4()), "namespaced_name": "provider::slow_tool"}

        await _execute_async_wrapper(
            tool_name="slow_tool",
            tool_call_id="call-2",
            exception=TimeoutError("Request timed out"),
            tool=tool,
        )

        mock_emit.assert_called_once()
        _, _, emit_status = mock_emit.call_args[0]
        assert emit_status == ToolExecutionStatus.TIMEOUT

        mock_persist.assert_awaited_once()
        persist_args = mock_persist.call_args
        assert persist_args[0][0] is tool
        assert persist_args[0][2] == ToolExecutionStatus.TIMEOUT
        assert persist_args[1]["error_message"] == "Request timed out"

    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._persist_tool_execution_to_db")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._emit_tool_metrics")
    async def test_async_wrapper_error_emits_error_status(self, mock_emit: Mock, mock_persist: AsyncMock) -> None:
        """Test that a generic exception emits ERROR status."""
        tool = Mock(spec=BaseTool)
        tool.name = "bad_tool"
        tool.metadata = {"tool_id": str(uuid4()), "namespaced_name": "provider::bad_tool"}

        await _execute_async_wrapper(
            tool_name="bad_tool",
            tool_call_id="call-3",
            exception=ValueError("bad input"),
            tool=tool,
        )

        mock_emit.assert_called_once()
        _, _, emit_status = mock_emit.call_args[0]
        assert emit_status == ToolExecutionStatus.ERROR

        mock_persist.assert_awaited_once()
        assert mock_persist.call_args[0][2] == ToolExecutionStatus.ERROR

    @pytest.mark.usefixtures("fast_retry_settings")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._run_coroutine_from_sync")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._emit_tool_metrics")
    def test_sync_wrapper_timeout_emits_timeout_status(self, mock_emit: Mock, mock_run_coro: Mock) -> None:
        """Test that sync wrapper maps TimeoutError to TIMEOUT status."""
        tool = Mock(spec=BaseTool)
        tool.name = "sync_slow"
        tool.metadata = {"tool_id": str(uuid4()), "namespaced_name": "provider::sync_slow"}

        _execute_sync_wrapper(
            tool_name="sync_slow",
            tool_call_id="call-5",
            exception=TimeoutError("sync timeout"),
            tool=tool,
        )

        mock_emit.assert_called_once()
        _, _, emit_status = mock_emit.call_args[0]
        assert emit_status == ToolExecutionStatus.TIMEOUT

        # _run_coroutine_from_sync is called twice: once for tool disable, once for DB persistence
        assert mock_run_coro.call_count == 2
        persist_call = mock_run_coro.call_args_list[-1]
        assert persist_call[0][2] == "tool execution DB persistence"

    @pytest.mark.usefixtures("fast_retry_settings")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._run_coroutine_from_sync")
    @patch("syntara.agent_orchestrator.tool_manager.execution_failure_handler._emit_tool_metrics")
    def test_sync_wrapper_value_error_skips_disable_but_persists(self, mock_emit: Mock, mock_run_coro: Mock) -> None:
        """ValueError still emits metrics/persists but does not schedule auto-disable."""
        tool = Mock(spec=BaseTool)
        tool.name = "sync_bad_args"
        tool.metadata = {"tool_id": str(uuid4()), "namespaced_name": "provider::sync_bad_args"}

        _execute_sync_wrapper(
            tool_name="sync_bad_args",
            tool_call_id="call-6",
            exception=ValueError("bad args"),
            tool=tool,
        )

        mock_emit.assert_called_once()
        _, _, emit_status = mock_emit.call_args[0]
        assert emit_status == ToolExecutionStatus.ERROR

        # Only DB persistence is scheduled; auto-disable is skipped for ValueError
        assert mock_run_coro.call_count == 1
        persist_call = mock_run_coro.call_args_list[0]
        assert persist_call[0][2] == "tool execution DB persistence"
