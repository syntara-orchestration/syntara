"""Unit tests for ToolDiscoveryEvent, ToolInvocationEvent and their handlers."""

# mypy: disable-error-code="attr-defined"

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from syntara.agent_orchestrator.audit.tool_management import (
    ToolDiscoveryEvent,
    ToolDiscoveryHandler,
    ToolDiscoveryStatus,
    ToolInvocationEvent,
    ToolInvocationHandler,
    ToolInvocationStatus,
)
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


@dataclass
class _FakeUser:
    """Minimal user object for unit tests — avoids DB fixture isolation issues."""

    id: UUID
    username: str
    email: str


@pytest.fixture
def test_user() -> _FakeUser:
    """Return a lightweight fake user — no DB interaction required."""
    return _FakeUser(id=uuid4(), username="test-user", email="test@example.com")


class TestToolDiscoveryHandler:
    """Tests for ToolDiscoveryHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """ToolDiscoveryHandler is a subclass of AuditEventHandler."""
        handler = ToolDiscoveryHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_started_status_with_user_actor(self, test_user: User) -> None:
        """Started tool discovery with USER actor produces INFO severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.STARTED,
            session_id="session-123",
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "tool_discovery"
        assert result.event_message == "Tool discovery and synchronization started"
        assert result.source_component == "syntara.agent_orchestrator.tool_manager"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username
        assert result.execution_id == execution_id
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "tool_discovery"
        assert result.structured_data.status == "started"
        assert result.structured_data.session_id == "session-123"
        assert result.structured_data.invocation_id == invocation_id
        assert result.structured_data.request_id == request_id
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    async def test_completed_status_with_metrics(self, test_user: User) -> None:
        """Completed tool discovery includes discovery metrics."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.COMPLETED,
            session_id="session-456",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            integrations_discovered=3,
            tools_discovered=15,
            tools_enabled=12,
            tools_disabled=2,
            tools_filtered=1,
            tools_provided_to_llm=12,
            tool_names=["read_file", "write_file", "execute_bash"],
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "Tool discovery completed - 12 tools provided to LLM"
        assert result.structured_data.status == "completed"
        assert result.structured_data.integrations_discovered == 3
        assert result.structured_data.tools_discovered == 15
        assert result.structured_data.tools_enabled == 12
        assert result.structured_data.tools_disabled == 2
        assert result.structured_data.tools_filtered == 1
        assert result.structured_data.tools_provided_to_llm == 12
        assert result.structured_data.tool_names == ["read_file", "write_file", "execute_bash"]

    async def test_failed_status_with_error(self, test_user: User) -> None:
        """Failed tool discovery produces ERROR severity with error details."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.FAILED,
            session_id="session-789",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            error_type="ToolManagerConnectionError",
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "tool_discovery"
        assert result.event_message == "Tool discovery and synchronization failed"
        assert result.structured_data.error_type == "ToolManagerConnectionError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
        assert result.structured_data.status == "failed"

    def test_completed_with_zero_tools(self) -> None:
        """Completed discovery with zero tools provided."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.COMPLETED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            tools_provided_to_llm=0,
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.event_message == "Tool discovery completed - 0 tools provided to LLM"
        assert result.structured_data.tools_provided_to_llm == 0

    def test_completed_without_tools_provided(self) -> None:
        """Completed discovery without tools_provided_to_llm field."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.COMPLETED,
            session_id="session-def",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.event_message == "Tool discovery completed - 0 tools provided to LLM"
        assert result.structured_data.tools_provided_to_llm is None

    def test_discovery_metrics_optional(self) -> None:
        """Discovery metrics are optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.STARTED,
            session_id="session-ghi",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.structured_data.integrations_discovered is None
        assert result.structured_data.tools_discovered is None
        assert result.structured_data.tools_enabled is None
        assert result.structured_data.tools_disabled is None
        assert result.structured_data.tools_filtered is None
        assert result.structured_data.tools_provided_to_llm is None
        assert result.structured_data.tool_names is None

    def test_no_actor_context(self) -> None:
        """Event without actor_context defaults to None actor fields."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.STARTED,
            session_id="session-jkl",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=None,
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_username is None
        assert result.actor_type is None

    def test_failed_without_error_type(self) -> None:
        """Failed status without explicit error_type still produces error event."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolDiscoveryEvent(
            status=ToolDiscoveryStatus.FAILED,
            session_id="session-mno",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            error_type=None,
        )

        handler = ToolDiscoveryHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None


class TestToolInvocationHandler:
    """Tests for ToolInvocationHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """ToolInvocationHandler is a subclass of AuditEventHandler."""
        handler = ToolInvocationHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_started_status_with_user_actor(self, test_user: User) -> None:
        """Started tool invocation with USER actor produces INFO severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="read_file",
            status=ToolInvocationStatus.STARTED,
            session_id="session-pqr",
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "tool_invocation"
        assert result.event_message == "Tool invocation started: read_file"
        assert result.source_component == "syntara.agent_orchestrator.tool_manager"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username
        assert result.execution_id == execution_id
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "tool_invocation"
        assert result.structured_data.tool_name == "read_file"
        assert result.structured_data.status == "started"
        assert result.structured_data.session_id == "session-pqr"
        assert result.structured_data.invocation_id == invocation_id
        assert result.structured_data.request_id == request_id
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    async def test_completed_status_with_input_output(self, test_user: User) -> None:
        """Completed tool invocation includes input and output."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="execute_bash",
            status=ToolInvocationStatus.COMPLETED,
            session_id="session-stu",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            tool_input={"command": "ls -la"},
            tool_output="total 128\ndrwxr-xr-x  5 user  staff  160 May 26 10:00 .",
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "Tool invocation completed: execute_bash"
        assert result.structured_data.status == "completed"
        assert result.structured_data.tool_input == {"command": "ls -la"}
        assert result.structured_data.tool_output == "total 128\ndrwxr-xr-x  5 user  staff  160 May 26 10:00 ."

    async def test_failed_status_with_error(self, test_user: User) -> None:
        """Failed tool invocation produces ERROR severity with error details."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="write_file",
            status=ToolInvocationStatus.FAILED,
            session_id="session-vwx",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            error_type="PermissionDenied",
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "tool_invocation"
        assert result.event_message == "Tool invocation failed: write_file"
        assert result.structured_data.error_type == "PermissionDenied"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
        assert result.structured_data.status == "failed"

    def test_tool_input_output_optional(self) -> None:
        """Tool input and output are optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="list_tools",
            status=ToolInvocationStatus.STARTED,
            session_id="session-yz",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.structured_data.tool_input is None
        assert result.structured_data.tool_output is None

    def test_no_actor_context(self) -> None:
        """Event without actor_context defaults to None actor fields."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="search",
            status=ToolInvocationStatus.STARTED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=None,
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_username is None
        assert result.actor_type is None

    def test_failed_without_error_type(self) -> None:
        """Failed status without explicit error_type still produces error event."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="unknown_tool",
            status=ToolInvocationStatus.FAILED,
            session_id="session-def",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            error_type=None,
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_execution_id_optional(self) -> None:
        """Execution ID is optional."""
        invocation_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="get_info",
            status=ToolInvocationStatus.STARTED,
            session_id="session-ghi",
            invocation_id=invocation_id,
            execution_id=None,
            actor_context=AuditActorContext(),
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.execution_id is None

    def test_complex_tool_input(self) -> None:
        """Tool input can be complex nested dict."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ToolInvocationEvent(
            tool_name="complex_operation",
            status=ToolInvocationStatus.COMPLETED,
            session_id="session-jkl",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            tool_input={
                "operation": "transform",
                "parameters": {"format": "json", "indent": 2, "sort_keys": True},
                "filters": [{"field": "status", "value": "active"}],
            },
        )

        handler = ToolInvocationHandler()
        result = handler.handle(event)

        assert result.structured_data.tool_input == {
            "operation": "transform",
            "parameters": {"format": "json", "indent": 2, "sort_keys": True},
            "filters": [{"field": "status", "value": "active"}],
        }
