"""Unit tests for settings router helpers.

Tests cover:
- setting_to_read: effective_value computation
- _validate_key: key format validation
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from syntara.settings.models.runtime_setting import RuntimeSetting, SettingCategory, SettingValueType
from syntara.settings.router import _validate_key
from syntara.settings.services.settings_service import setting_to_read


def _make_setting(
    key: str = "context_manager.max_total_tokens",
    value: object = None,
    default_value: object = 4000,
) -> RuntimeSetting:
    """Build a RuntimeSetting for test assertions."""
    now = datetime.now(UTC)
    return RuntimeSetting(
        id=uuid4(),
        name="Max total tokens",
        key=key,
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        value=value,
        default_value=default_value,
        group="Token limits",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# setting_to_read
# ---------------------------------------------------------------------------


class TestSettingToRead:
    """Tests for the setting_to_read converter."""

    def test_effective_value_uses_value_when_set(self) -> None:
        """effective_value is value when value is not None."""
        setting = _make_setting(value=8000, default_value=4000)
        read = setting_to_read(setting)

        assert read.effective_value == 8000
        assert read.value == 8000
        assert read.default_value == 4000

    def test_effective_value_uses_default_when_none(self) -> None:
        """effective_value falls back to default_value when value is None."""
        setting = _make_setting(value=None, default_value=4000)
        read = setting_to_read(setting)

        assert read.effective_value == 4000
        assert read.value is None

    def test_group_field_included(self) -> None:
        """Group field is included in the read schema."""
        setting = _make_setting()
        read = setting_to_read(setting)

        assert read.group == "Token limits"

    def test_depends_on_field_included(self) -> None:
        """depends_on field is included in the read schema."""
        setting = _make_setting()
        setting.depends_on = "context_manager.enable_hybrid_search"
        read = setting_to_read(setting)

        assert read.depends_on == "context_manager.enable_hybrid_search"

    def test_depends_on_none_when_not_set(self) -> None:
        """depends_on is None when not set on the setting."""
        setting = _make_setting()
        read = setting_to_read(setting)

        assert read.depends_on is None

    def test_category_serialized_as_string(self) -> None:
        """Category enum is serialized as its string value."""
        setting = _make_setting()
        read = setting_to_read(setting)

        assert read.category == "context_manager"


# ---------------------------------------------------------------------------
# _validate_key
# ---------------------------------------------------------------------------


class TestValidateKey:
    """Tests for the _validate_key helper."""

    def test_valid_dot_namespaced_key(self) -> None:
        """A valid dot-namespaced key passes."""
        _validate_key("context_manager.max_total_tokens")

    def test_valid_two_segment_key(self) -> None:
        """A two-segment key passes."""
        _validate_key("system.debug")

    def test_rejects_single_segment(self) -> None:
        """A key without a dot is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_key("nodot")
        assert exc_info.value.status_code == 400

    def test_rejects_path_traversal(self) -> None:
        """Path traversal attempts are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_key("../../../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_rejects_uppercase(self) -> None:
        """Uppercase keys are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_key("Context_Manager.Max_Tokens")
        assert exc_info.value.status_code == 400

    def test_rejects_empty_string(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_key("")
        assert exc_info.value.status_code == 400
