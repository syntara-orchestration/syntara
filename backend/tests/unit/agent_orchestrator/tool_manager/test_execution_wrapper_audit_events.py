"""Unit tests for tool execution wrapper audit event dispatch.

Verifies that create_tool_awrapper and create_tool_wrapper emit the expected audit events:
- ToolInvocationEvent (STARTED, COMPLETED, FAILED) for both async and sync wrappers
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import ToolCall
from langchain_core.messages.tool import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from syntara.agent_orchestrator.audit.tool_management import (
    ToolInvocationEvent,
    ToolInvocationHandler,
)
from syntara.agent_orchestrator.tool_manager.execution_failure_handler import (
    create_tool_awrapper,
    create_tool_wrapper,
)
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus


def _make_tool_call_request(tool_name: str, tool_args: dict[str, Any] | None = None) -> ToolCallRequest:
    """Build a minimal ToolCallRequest for testing."""
    mock_tool = MagicMock()
    mock_tool.name = tool_name

    tool_call = ToolCall(
        name=tool_name,
        args=tool_args or {},
        id=f"call_{tool_name}",
    )

    return ToolCallRequest(
        tool_call=tool_call,
        tool=mock_tool,
        state={},
        runtime=Mock(),
    )


class TestAsyncToolInvocationEventDispatch:
    """Test ToolInvocationEvent emission from create_tool_awrapper()."""

    def setup_method(self) -> None:
        """Register audit event handlers."""
        AuditEventDispatcher.register(
            {
                ToolInvocationEvent: ToolInvocationHandler(),
            }
        )

    @pytest.mark.asyncio
    async def test_async_wrapper_emits_started_and_completed_events(self) -> None:
        """Successful async tool execution emits STARTED and COMPLETED events."""
        session_id = "sess-async-123"
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()

        # Create wrapper
        wrapper = create_tool_awrapper(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
        )

        # Create mock tool request and execution function
        request = _make_tool_call_request("read_file", {"path": "/tmp/test.txt"})  # noqa: S108

        async def mock_execute(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(content="File content here", tool_call_id=req.tool_call["id"])

        with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
            result = await wrapper(request, mock_execute)

        # Verify result
        assert isinstance(result, ToolMessage)
        assert result.content == "File content here"

        # Verify events emitted
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        invocation_events = [e for e in events if e.event_action == "tool_invocation"]

        assert len(invocation_events) == 2

        # Event 1: STARTED
        started_event = invocation_events[0]
        assert started_event.event_category == EventCategory.AGENT_INTERACTION
        assert started_event.event_severity == EventSeverity.INFO
        assert started_event.event_status == EventStatus.SUCCESS
        assert started_event.event_message == "Tool invocation started: read_file"
        assert started_event.structured_data.tool_name == "read_file"  # type: ignore[attr-defined]
        assert started_event.structured_data.status == "started"  # type: ignore[attr-defined]
        assert started_event.structured_data.tool_input == {"path": "/tmp/test.txt"}  # type: ignore[attr-defined]  # noqa: S108
        assert started_event.structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
        assert started_event.structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
        assert started_event.execution_id == execution_id
        assert started_event.structured_data.request_id == str(request_id)  # type: ignore[attr-defined]

        # Event 2: COMPLETED
        completed_event = invocation_events[1]
        assert completed_event.event_severity == EventSeverity.INFO
        assert completed_event.event_status == EventStatus.SUCCESS
        assert completed_event.event_message == "Tool invocation completed: read_file"
        assert completed_event.structured_data.status == "completed"  # type: ignore[attr-defined]
        assert completed_event.structured_data.tool_output == "File content here"  # type: ignore[attr-defined]
        assert completed_event.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert completed_event.execution_id == execution_id
        assert completed_event.structured_data.request_id == str(request_id)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_async_wrapper_emits_failed_event_on_error(self) -> None:
        """Failed async tool execution emits STARTED and FAILED events."""
        session_id = "sess-async-fail"
        invocation_id = uuid4()
        execution_id = uuid4()

        # Create wrapper
        wrapper = create_tool_awrapper(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
        )

        # Create mock tool request that will fail
        request = _make_tool_call_request("write_file", {"path": "/tmp/test.txt", "content": "data"})  # noqa: S108

        async def mock_execute(req: ToolCallRequest) -> ToolMessage:
            msg = "Access denied"
            raise PermissionError(msg)

        # Mock the tool disable functionality to avoid side effects
        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch(
                "syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id",
                new_callable=AsyncMock,
            ),
        ):
            result = await wrapper(request, mock_execute)

        # Verify error message returned
        assert isinstance(result, ToolMessage)
        content_str = result.content if isinstance(result.content, str) else str(result.content)
        assert "error" in content_str.lower() or "failed" in content_str.lower()

        # Verify events emitted
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        invocation_events = [e for e in events if e.event_action == "tool_invocation"]

        assert len(invocation_events) == 2

        # Event 1: STARTED
        assert invocation_events[0].structured_data.status == "started"  # type: ignore[attr-defined]

        # Event 2: FAILED
        failed_event = invocation_events[1]
        assert failed_event.event_category == EventCategory.AGENT_INTERACTION
        assert failed_event.event_severity == EventSeverity.ERROR
        assert failed_event.event_status == EventStatus.ERROR
        assert failed_event.event_message == "Tool invocation failed: write_file"
        assert failed_event.structured_data.status == "failed"  # type: ignore[attr-defined]
        assert failed_event.structured_data.error_type == "PermissionError"
        assert failed_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    @pytest.mark.asyncio
    async def test_async_wrapper_session_id_propagation(self) -> None:
        """session_id and invocation_id are correctly included in async wrapper events."""
        session_id = "sess-async-prop"
        invocation_id = uuid4()

        wrapper = create_tool_awrapper(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=None,  # No execution_id
        )

        request = _make_tool_call_request("test_tool")

        async def mock_execute(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(content="result", tool_call_id=req.tool_call["id"])

        with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
            await wrapper(request, mock_execute)

        # Verify all events contain session_id and invocation_id
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        invocation_events = [e for e in events if e.event_action == "tool_invocation"]

        assert len(invocation_events) == 2
        for event in invocation_events:
            assert event.structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
            assert event.structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
            assert event.execution_id is None
            assert event.resource_urn == f"urn:syntara:invocation:{invocation_id}"


class TestSyncToolInvocationEventDispatch:
    """Test ToolInvocationEvent emission from create_tool_wrapper()."""

    def setup_method(self) -> None:
        """Register audit event handlers."""
        AuditEventDispatcher.register(
            {
                ToolInvocationEvent: ToolInvocationHandler(),
            }
        )

    def test_sync_wrapper_emits_started_and_completed_events(self) -> None:
        """Successful sync tool execution emits STARTED and COMPLETED events."""
        session_id = "sess-sync-123"
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()

        # Create wrapper
        wrapper = create_tool_wrapper(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
        )

        # Create mock tool request and execution function
        request = _make_tool_call_request("execute_bash", {"command": "ls -la"})

        def mock_execute(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(content="total 128\ndrwxr-xr-x  5 user", tool_call_id=req.tool_call["id"])

        with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
            result = wrapper(request, mock_execute)

        # Verify result
        assert isinstance(result, ToolMessage)
        assert "total 128" in result.content

        # Verify events emitted
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        invocation_events = [e for e in events if e.event_action == "tool_invocation"]

        assert len(invocation_events) == 2

        # Event 1: STARTED
        started_event = invocation_events[0]
        assert started_event.event_category == EventCategory.AGENT_INTERACTION
        assert started_event.event_severity == EventSeverity.INFO
        assert started_event.event_status == EventStatus.SUCCESS
        assert started_event.event_message == "Tool invocation started: execute_bash"
        assert started_event.structured_data.tool_name == "execute_bash"  # type: ignore[attr-defined]
        assert started_event.structured_data.status == "started"  # type: ignore[attr-defined]
        assert started_event.structured_data.tool_input == {"command": "ls -la"}  # type: ignore[attr-defined]
        assert started_event.execution_id == execution_id
        assert started_event.structured_data.request_id == str(request_id)  # type: ignore[attr-defined]

        # Event 2: COMPLETED
        completed_event = invocation_events[1]
        assert completed_event.event_severity == EventSeverity.INFO
        assert completed_event.event_status == EventStatus.SUCCESS
        assert completed_event.event_message == "Tool invocation completed: execute_bash"
        assert completed_event.structured_data.status == "completed"  # type: ignore[attr-defined]
        assert "total 128" in completed_event.structured_data.tool_output  # type: ignore[attr-defined]
        assert completed_event.execution_id == execution_id
        assert completed_event.structured_data.request_id == str(request_id)  # type: ignore[attr-defined]

    def test_sync_wrapper_emits_failed_event_on_error(self) -> None:
        """Failed sync tool execution emits STARTED and FAILED events."""
        session_id = "sess-sync-fail"
        invocation_id = uuid4()

        # Create wrapper
        wrapper = create_tool_wrapper(
            session_id=session_id,
            invocation_id=invocation_id,
        )

        # Create mock tool request that will fail
        request = _make_tool_call_request("risky_tool")

        def mock_execute(req: ToolCallRequest) -> ToolMessage:
            msg = "Invalid operation"
            raise ValueError(msg)

        # Mock the tool disable functionality to avoid side effects
        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch(
                "syntara.agent_orchestrator.tool_manager.execution_failure_handler._disable_tool_by_id",
                new_callable=AsyncMock,
            ),
        ):
            result = wrapper(request, mock_execute)

        # Verify error message returned
        assert isinstance(result, ToolMessage)
        content_str = result.content if isinstance(result.content, str) else str(result.content)
        assert "error" in content_str.lower() or "failed" in content_str.lower()

        # Verify events emitted
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        invocation_events = [e for e in events if e.event_action == "tool_invocation"]

        assert len(invocation_events) == 2

        # Event 1: STARTED
        assert invocation_events[0].structured_data.status == "started"  # type: ignore[attr-defined]

        # Event 2: FAILED
        failed_event = invocation_events[1]
        assert failed_event.event_category == EventCategory.AGENT_INTERACTION
        assert failed_event.event_severity == EventSeverity.ERROR
        assert failed_event.event_status == EventStatus.ERROR
        assert failed_event.event_message == "Tool invocation failed: risky_tool"
        assert failed_event.structured_data.status == "failed"  # type: ignore[attr-defined]
        assert failed_event.structured_data.error_type == "ValueError"
        assert failed_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_sync_wrapper_complex_tool_input(self) -> None:
        """Sync wrapper handles complex nested tool input."""
        session_id = "sess-complex"
        invocation_id = uuid4()

        wrapper = create_tool_wrapper(
            session_id=session_id,
            invocation_id=invocation_id,
        )

        complex_input = {
            "operation": "transform",
            "parameters": {"format": "json", "indent": 2},
            "filters": [{"field": "status", "value": "active"}],
        }
        request = _make_tool_call_request("complex_tool", complex_input)

        def mock_execute(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(content="transformed", tool_call_id=req.tool_call["id"])

        with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
            wrapper(request, mock_execute)

        # Verify complex input preserved in event
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        started_events = [
            e
            for e in events
            if e.event_action == "tool_invocation" and e.structured_data.status == "started"  # type: ignore[attr-defined]
        ]

        assert len(started_events) == 1
        assert started_events[0].structured_data.tool_input == complex_input  # type: ignore[attr-defined]

    def test_sync_wrapper_session_id_propagation(self) -> None:
        """session_id and invocation_id are correctly included in sync wrapper events."""
        session_id = "sess-sync-prop"
        invocation_id = uuid4()

        wrapper = create_tool_wrapper(
            session_id=session_id,
            invocation_id=invocation_id,
        )

        request = _make_tool_call_request("test_tool")

        def mock_execute(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(content="result", tool_call_id=req.tool_call["id"])

        with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
            wrapper(request, mock_execute)

        # Verify all events contain session_id and invocation_id
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        invocation_events = [e for e in events if e.event_action == "tool_invocation"]

        assert len(invocation_events) == 2
        for event in invocation_events:
            assert event.structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
            assert event.structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
            assert event.resource_urn == f"urn:syntara:invocation:{invocation_id}"
