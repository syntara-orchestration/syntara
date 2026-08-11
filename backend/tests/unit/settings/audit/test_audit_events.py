"""Unit tests for settings-domain audit events, handlers, and sanitization.

Tests cover:
- SettingChangeHandler: correct AuditEvent mapping for success and error cases
- SettingBulkChangeHandler: correct AuditEvent mapping for success and error cases
- Handler zero-arg construction
- Auto-discovery of settings audit handlers
- _sanitize_setting_value: redaction, truncation, None handling
"""

from __future__ import annotations

from syntara.audit.discovery import discover_handlers
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.settings.audit.settings import (
    SettingBulkChangeEvent,
    SettingBulkChangeHandler,
    SettingChangeEvent,
    SettingChangeHandler,
)
from syntara.settings.services.settings_service import _format_setting_value

# ---------------------------------------------------------------------------
# SettingChangeHandler
# ---------------------------------------------------------------------------


class TestSettingChangeHandler:
    """Tests for SettingChangeHandler mapping."""

    def _make_event(self, **overrides: object) -> SettingChangeEvent:
        defaults: dict[str, object] = {
            "setting": "ai.model_name",
            "old_value": "gpt-4",
            "new_value": "claude-3.5-sonnet",
            "category": "ai_llm",
            "value_type": "string",
            "version": 2,
        }
        defaults.update(overrides)
        return SettingChangeEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        handler = SettingChangeHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event is not None
        assert audit_event.event_action == "setting_changed"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.settings"
        assert "ai.model_name" in audit_event.event_message

    def test_resource_fields(self) -> None:
        handler = SettingChangeHandler()
        event = self._make_event(resource_name="AI Model Name")

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == "urn:syntara:setting:ai_llm:ai.model_name"
        assert audit_event.resource_name == "AI Model Name"

    def test_resource_urn_without_category(self) -> None:
        handler = SettingChangeHandler()
        event = self._make_event(category=None)

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == "urn:syntara:setting:ai.model_name"

    def test_structured_data_fields(self) -> None:
        handler = SettingChangeHandler()
        event = self._make_event()

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "setting-changed"
        assert data.setting == "ai.model_name"  # type: ignore[attr-defined]
        assert data.old_value == "gpt-4"  # type: ignore[attr-defined]
        assert data.new_value == "claude-3.5-sonnet"  # type: ignore[attr-defined]
        assert data.category == "ai_llm"  # type: ignore[attr-defined]
        assert data.value_type == "string"  # type: ignore[attr-defined]
        assert data.version == 2  # type: ignore[attr-defined]

    def test_error_event(self) -> None:
        handler = SettingChangeHandler()
        event = self._make_event(error_type="SettingValidationError")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.structured_data.error_type == "SettingValidationError"

    def test_zero_arg_constructable(self) -> None:
        handler = SettingChangeHandler()
        assert isinstance(handler, SettingChangeHandler)


# ---------------------------------------------------------------------------
# SettingBulkChangeHandler
# ---------------------------------------------------------------------------


class TestSettingBulkChangeHandler:
    """Tests for SettingBulkChangeHandler mapping."""

    def _make_event(self, **overrides: object) -> SettingBulkChangeEvent:
        defaults: dict[str, object] = {
            "settings": ["ai.model_name", "ai.temperature"],
            "change_count": 2,
        }
        defaults.update(overrides)
        return SettingBulkChangeEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        handler = SettingBulkChangeHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event is not None
        assert audit_event.event_action == "setting_bulk_changed"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.settings"
        assert "2 setting(s)" in audit_event.event_message

    def test_structured_data_fields(self) -> None:
        handler = SettingBulkChangeHandler()
        event = self._make_event()

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "setting-bulk-changed"
        assert data.settings == ["ai.model_name", "ai.temperature"]  # type: ignore[attr-defined]
        assert data.change_count == 2  # type: ignore[attr-defined]

    def test_error_event(self) -> None:
        handler = SettingBulkChangeHandler()
        event = self._make_event(error_type="OptimisticLockError")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR

    def test_zero_arg_constructable(self) -> None:
        handler = SettingBulkChangeHandler()
        assert isinstance(handler, SettingBulkChangeHandler)


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------


class TestSettingsAuditDiscovery:
    """Tests for automatic discovery of settings audit handlers."""

    def test_discovers_both_handlers(self) -> None:
        import syntara.settings.audit

        registry = discover_handlers(syntara.settings.audit)

        assert SettingChangeEvent in registry
        assert SettingBulkChangeEvent in registry
        assert len(registry) == 2

    def test_discovered_handler_types(self) -> None:
        import syntara.settings.audit

        registry = discover_handlers(syntara.settings.audit)

        assert isinstance(registry[SettingChangeEvent], SettingChangeHandler)
        assert isinstance(registry[SettingBulkChangeEvent], SettingBulkChangeHandler)


# ---------------------------------------------------------------------------
# _format_setting_value
# ---------------------------------------------------------------------------


class TestFormatSettingValue:
    """Tests for the setting value formatting helper."""

    def test_none_value_returns_none(self) -> None:
        assert _format_setting_value(None) is None

    def test_string_value(self) -> None:
        assert _format_setting_value("claude-3.5") == "claude-3.5"

    def test_converts_to_string(self) -> None:
        assert _format_setting_value(0.7) == "0.7"

    def test_truncates_long_values(self) -> None:
        long_value = "x" * 300
        result = _format_setting_value(long_value)
        assert result is not None
        assert len(result) == 256
        assert result.endswith("...")

    def test_short_value_not_truncated(self) -> None:
        value = "x" * 256
        result = _format_setting_value(value)
        assert result == value

    def test_boolean_value(self) -> None:
        value = True
        assert _format_setting_value(value) == "True"

    def test_integer_value(self) -> None:
        assert _format_setting_value(4096) == "4096"
