"""Unit tests for ToolRetriever audit event dispatch.

Verifies that ToolRetriever emits the expected audit events during execution:
- ToolDiscoveryEvent (STARTED, COMPLETED, FAILED)
"""

from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.audit.tool_management import (
    ToolDiscoveryEvent,
    ToolDiscoveryHandler,
)
from syntara.agent_orchestrator.tool_manager.tool_services import ToolRetriever
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus


@pytest.fixture
def mock_tool_sync_internals() -> Callable[..., Any]:
    """Fixture that patches all ToolRetriever internal functions with configurable behavior.

    Returns a context manager factory that accepts overrides for specific patches.

    Usage:
        with mock_tool_sync_internals({"discover_providers": {"side_effect": ValueError("error")}}):
            # Test code here

    Supported patch names:
        - discover_integrations: _discover_mcp_integrations
        - discover_tools: _discover_tools
        - retrieve_base_tools: _retrieve_base_tools_from_integrations
        - filter_enabled: _filter_enabled_tools
        - enhance_metadata: _enhance_tools_with_metadata
    """

    @contextmanager
    def _create_patches(overrides: dict[str, Any] | None = None) -> Generator[None, None, None]:
        """Create patches with optional overrides.

        Args:
            overrides: Dict mapping patch names to configuration. Each value can be:
                - A dict with AsyncMock/Mock kwargs (e.g., {"return_value": [], "side_effect": ...})
                - A direct value to use as return_value

        Supported patch names:
            - discover_integrations: _discover_mcp_integrations
            - discover_tools: _discover_tools
            - retrieve_base_tools: _retrieve_base_tools_from_integrations
            - filter_enabled: _filter_enabled_tools
            - enhance_metadata: _enhance_tools_with_metadata

        """
        overrides = overrides or {}

        def _get_patch_config(name: str, default_return: Any, *, is_async: bool = True) -> dict[str, Any]:  # noqa: ANN401
            """Get patch configuration with defaults."""
            override = overrides.get(name, {})
            if not isinstance(override, dict):
                # Direct value provided, treat as return_value
                override = {"return_value": override}

            if is_async:
                config: dict[str, Any] = {"new_callable": AsyncMock}
            else:
                config = {"new_callable": MagicMock}

            if "side_effect" not in override:
                config["return_value"] = override.get("return_value", default_return)
            else:
                config["side_effect"] = override["side_effect"]

            return config

        patches = [
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._discover_mcp_integrations",
                **_get_patch_config("discover_providers", [], is_async=True),
            ),
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._discover_tools",
                **_get_patch_config("discover_tools", ([], []), is_async=True),
            ),
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._retrieve_base_tools_from_integrations",
                **_get_patch_config("retrieve_base_tools", [], is_async=True),
            ),
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._filter_enabled_tools",
                **_get_patch_config("filter_enabled", [], is_async=False),
            ),
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._enhance_tools_with_metadata",
                **_get_patch_config("enhance_metadata", [], is_async=False),
            ),
        ]

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            yield

    return _create_patches


class TestToolDiscoveryEventDispatch:
    """Test ToolDiscoveryEvent emission from ToolRetriever.retrieve_tools()."""

    def setup_method(self) -> None:
        """Register audit event handlers."""
        AuditEventDispatcher.register(
            {
                ToolDiscoveryEvent: ToolDiscoveryHandler(),
            }
        )

    @pytest.mark.asyncio
    async def test_retrieve_emits_started_and_completed_events(
        self, mock_tool_sync_internals: Callable[..., Any]
    ) -> None:
        """Successful retrieval emits STARTED and COMPLETED events."""
        session_id = "sess-sync-123"
        invocation_id = uuid4()
        execution_id = uuid4()

        retriever = ToolRetriever(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
        )

        # Mock data for successful retrieval
        mock_providers = [
            {"id": "provider1", "name": "Provider 1"},
            {"id": "provider2", "name": "Provider 2"},
        ]
        mock_enabled_tools = [
            {"id": "tool1", "name": "read_file", "status": "enabled"},
            {"id": "tool2", "name": "write_file", "status": "enabled"},
            {"id": "tool3", "name": "execute_bash", "status": "enabled"},
        ]
        mock_disabled_tools = [
            {"id": "tool4", "name": "disabled_tool", "status": "disabled"},
        ]
        mock_namespaced_tools = [
            AsyncMock(name="provider1:read_file"),
            AsyncMock(name="provider1:write_file"),
            AsyncMock(name="provider2:execute_bash"),
        ]

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            mock_tool_sync_internals(
                {
                    "discover_providers": mock_providers,
                    "discover_tools": (mock_enabled_tools, mock_disabled_tools),
                    "retrieve_base_tools": mock_namespaced_tools,
                    "filter_enabled": mock_namespaced_tools[:3],
                    "enhance_metadata": mock_namespaced_tools[:3],
                }
            ),
        ):
            result = await retriever.retrieve_tools()

        # Verify tools returned
        assert len(result) == 3

        # Verify events emitted
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        discovery_events = [e for e in events if e.event_action == "tool_discovery"]

        assert len(discovery_events) == 2

        # Event 1: STARTED
        started_event = discovery_events[0]
        assert started_event.event_category == EventCategory.AGENT_INTERACTION
        assert started_event.event_severity == EventSeverity.INFO
        assert started_event.event_status == EventStatus.SUCCESS
        assert started_event.event_message == "Tool discovery and synchronization started"
        assert started_event.structured_data.status == "started"  # type: ignore[attr-defined]
        assert started_event.structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
        assert started_event.structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]

        # Event 2: COMPLETED with metrics
        completed_event = discovery_events[1]
        assert completed_event.event_severity == EventSeverity.INFO
        assert completed_event.event_status == EventStatus.SUCCESS
        assert completed_event.event_message == "Tool discovery completed - 3 tools provided to LLM"
        assert completed_event.structured_data.status == "completed"  # type: ignore[attr-defined]
        assert completed_event.structured_data.integrations_discovered == 2  # type: ignore[attr-defined]
        assert completed_event.structured_data.tools_discovered == 3  # type: ignore[attr-defined]
        assert completed_event.structured_data.tools_enabled == 3  # type: ignore[attr-defined]
        assert completed_event.structured_data.tools_disabled == 1  # type: ignore[attr-defined]
        assert completed_event.structured_data.tools_filtered == 3  # type: ignore[attr-defined]
        assert completed_event.structured_data.tools_provided_to_llm == 3  # type: ignore[attr-defined]
        assert len(completed_event.structured_data.tool_names) == 3  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_retrieve_emits_failed_event_on_error(self, mock_tool_sync_internals: Callable[..., Any]) -> None:
        """Failed retrieval emits STARTED and FAILED events."""
        session_id = "sess-sync-fail"
        invocation_id = uuid4()
        execution_id = uuid4()

        retriever = ToolRetriever(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
        )

        # Mock _discover_mcp_integrations to raise exception
        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            mock_tool_sync_internals(
                {"discover_providers": {"side_effect": ConnectionError("Tool Manager unavailable")}}
            ),
        ):
            result = await retriever.retrieve_tools()

        # Verify empty list returned (graceful degradation)
        assert result == []

        # Verify events emitted
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        discovery_events = [e for e in events if e.event_action == "tool_discovery"]

        assert len(discovery_events) == 2

        # Event 1: STARTED
        assert discovery_events[0].structured_data.status == "started"  # type: ignore[attr-defined]

        # Event 2: FAILED
        failed_event = discovery_events[1]
        assert failed_event.event_category == EventCategory.AGENT_INTERACTION
        assert failed_event.event_severity == EventSeverity.ERROR
        assert failed_event.event_status == EventStatus.ERROR
        assert failed_event.event_message == "Tool discovery and synchronization failed"
        assert failed_event.structured_data.status == "failed"  # type: ignore[attr-defined]
        assert failed_event.structured_data.error_type == "ConnectionError"
        assert failed_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    @pytest.mark.asyncio
    async def test_context_identifiers_in_discovery_events(self, mock_tool_sync_internals: Callable[..., Any]) -> None:
        """session_id, invocation_id, execution_id and resource_urn are correctly propagated."""
        session_id = "sess-propagation-456"
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()

        retriever = ToolRetriever(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
        )

        # Mock minimal successful retrieval (defaults provide empty lists)
        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            mock_tool_sync_internals(),
        ):
            await retriever.retrieve_tools()

        # Verify all events contain session_id, invocation_id, execution_id and request_id
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        discovery_events = [e for e in events if e.event_action == "tool_discovery"]

        assert len(discovery_events) == 2
        for event in discovery_events:
            assert event.structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
            assert event.structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
            assert event.structured_data.request_id == str(request_id)  # type: ignore[attr-defined]
            assert event.execution_id == execution_id
            assert event.resource_urn == f"urn:syntara:invocation:{invocation_id}"

    @pytest.mark.asyncio
    async def test_completed_event_with_zero_tools(self, mock_tool_sync_internals: Callable[..., Any]) -> None:
        """COMPLETED event handles zero tools gracefully."""
        session_id = "sess-zero-tools"
        invocation_id = uuid4()

        retriever = ToolRetriever(
            session_id=session_id,
            invocation_id=invocation_id,
        )

        # Mock retrieval that finds no tools (defaults provide empty lists)
        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            mock_tool_sync_internals(),
        ):
            result = await retriever.retrieve_tools()

        assert result == []

        # Verify COMPLETED event message reflects zero tools
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        completed_events = [
            e
            for e in events
            if e.event_action == "tool_discovery" and e.structured_data.status == "completed"  # type: ignore[attr-defined]
        ]

        assert len(completed_events) == 1
        assert completed_events[0].event_message == "Tool discovery completed - 0 tools provided to LLM"
        assert completed_events[0].structured_data.tools_provided_to_llm == 0  # type: ignore[attr-defined]
