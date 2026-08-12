"""Unit tests for AuditEventDispatcher dispatch and lifecycle management."""

from dataclasses import dataclass
from unittest.mock import patch

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class _DispatchEvent:
    message: str


@dataclass
class _OtherEvent:
    value: int


@dataclass
class _UnknownEvent:
    pass


class _DispatchHandler(AuditEventHandler["_DispatchEvent"]):
    def handle(self, event: "_DispatchEvent") -> AuditEvent:
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="dispatched",
            event_message=event.message,
            source_component="test",
            structured_data=AuditContextData(data_type="test"),
        )


class _OtherHandler(AuditEventHandler["_OtherEvent"]):
    def handle(self, event: "_OtherEvent") -> AuditEvent:
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="other",
            event_message=str(event.value),
            source_component="test",
            structured_data=AuditContextData(data_type="test"),
        )


class _SideEffectHandler(AuditEventHandler["_DispatchEvent"]):
    """Handler that returns None (side-effect only, e.g. telemetry)."""

    def __init__(self) -> None:
        self.called = False

    def handle(self, event: "_DispatchEvent") -> AuditEvent | None:
        self.called = True
        return None


class TestAuditEventDispatcher:
    """Tests for AuditEventDispatcher.dispatch() logic."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({_DispatchEvent: _DispatchHandler()})

    def test_dispatches_to_matching_handler(self) -> None:
        """dispatch() finds the correct handler and calls emit_audit_event."""
        with patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit:
            AuditEventDispatcher.dispatch(_DispatchEvent(message="hello"))

        mock_emit.assert_called_once()
        emitted = mock_emit.call_args[0][0]
        assert isinstance(emitted, AuditEvent)
        assert emitted.event_action == "dispatched"
        assert emitted.event_message == "hello"

    def test_unknown_event_type_does_not_raise(self) -> None:
        """dispatch() silently skips events with no registered handler."""
        with patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit:
            AuditEventDispatcher.dispatch(_UnknownEvent())

        mock_emit.assert_not_called()

    def test_unknown_event_type_logs_warning(self) -> None:
        """dispatch() logs a warning for unhandled event types."""
        AuditEventDispatcher._reset()

        with patch("syntara.audit.dispatcher.logger") as mock_logger:
            AuditEventDispatcher.dispatch(_UnknownEvent())

        mock_logger.warning.assert_called_once()

    def test_handler_raises_logs_exception_and_does_not_propagate(self) -> None:
        """When a handler.handle() raises, dispatch logs and swallows the error."""
        AuditEventDispatcher._reset()

        class _RaisingHandler(AuditEventHandler["_DispatchEvent"]):
            def handle(self, event: "_DispatchEvent") -> AuditEvent:
                msg = "boom"
                raise RuntimeError(msg)

        AuditEventDispatcher.register({_DispatchEvent: _RaisingHandler()})

        with (
            patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit,
            patch("syntara.audit.dispatcher.logger") as mock_logger,
        ):
            AuditEventDispatcher.dispatch(_DispatchEvent(message="x"))

        mock_emit.assert_not_called()
        mock_logger.exception.assert_called_once()

    def test_multiple_handlers_for_same_event_type(self) -> None:
        """dispatch() invokes all registered handlers for an event type."""
        side_effect_handler = _SideEffectHandler()
        AuditEventDispatcher.register({_DispatchEvent: _DispatchHandler()})
        AuditEventDispatcher.register({_DispatchEvent: side_effect_handler})

        with patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit:
            AuditEventDispatcher.dispatch(_DispatchEvent(message="multi"))

        # Only the first handler returns an AuditEvent; the side-effect handler returns None
        mock_emit.assert_called_once()
        assert mock_emit.call_args[0][0].event_action == "dispatched"
        assert side_effect_handler.called

    def test_side_effect_only_handler_skips_emit(self) -> None:
        """Handlers returning None do not trigger emit_audit_event."""
        AuditEventDispatcher._reset()

        side_effect_handler = _SideEffectHandler()
        AuditEventDispatcher.register({_DispatchEvent: side_effect_handler})

        with patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit:
            AuditEventDispatcher.dispatch(_DispatchEvent(message="no-audit"))

        mock_emit.assert_not_called()
        assert side_effect_handler.called


class TestDispatcherLifecycle:
    """Tests for register/reset lifecycle."""

    def test_register_merges_across_calls(self) -> None:
        """register() adds handlers without clearing previous registrations."""
        AuditEventDispatcher.register({_DispatchEvent: _DispatchHandler()})
        AuditEventDispatcher.register({_OtherEvent: _OtherHandler()})

        with patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit:
            AuditEventDispatcher.dispatch(_DispatchEvent(message="hi"))
            AuditEventDispatcher.dispatch(_OtherEvent(value=42))

        assert mock_emit.call_count == 2
        actions = [call.args[0].event_action for call in mock_emit.call_args_list]
        assert actions == ["dispatched", "other"]

    def test_reset_clears_registry(self) -> None:
        """reset() empties the registry so subsequent dispatches find nothing."""
        AuditEventDispatcher.register({_DispatchEvent: _DispatchHandler()})
        AuditEventDispatcher._reset()

        with patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit:
            AuditEventDispatcher.dispatch(_DispatchEvent(message="after reset"))

        mock_emit.assert_not_called()

    def test_register_is_idempotent(self) -> None:
        """register() is idempotent - registering same handler type twice doesn't duplicate."""
        # Register the same handler type twice
        AuditEventDispatcher.register({_DispatchEvent: _DispatchHandler()})
        AuditEventDispatcher.register({_DispatchEvent: _DispatchHandler()})

        with patch("syntara.audit.dispatcher.emit_audit_event") as mock_emit:
            AuditEventDispatcher.dispatch(_DispatchEvent(message="test"))

        # Should only emit once, not twice (no duplicate handlers)
        mock_emit.assert_called_once()
