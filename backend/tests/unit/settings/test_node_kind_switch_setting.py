"""Tests for the node-kind kill switch runtime setting (ANSTRAT-1750).

Covers the ``workflows.disabled_node_kinds`` catalog entry and the
``allowed_items`` constraint that backs it.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from syntara.settings.catalog import (
    DISABLED_NODE_KINDS_KEY,
    SETTINGS_CATALOG,
    SWITCHABLE_NODE_KINDS,
    WorkflowEngineGroup,
)
from syntara.settings.exceptions import SettingValidationError
from syntara.settings.models.runtime_setting import SettingCategory, SettingValueType
from syntara.settings.validators import check_schema_compatibility, validate_setting_value
from syntara.workflows.node_kind_switch import DISABLED_NODE_KINDS_SETTING_KEY, is_kind_switchable
from syntara.workflows.node_kinds import NODE_KINDS

_catalog_by_key = {defn.key: defn for defn in SETTINGS_CATALOG}


class TestDisabledNodeKindsCatalogEntry:
    """The kill switch is registered as a runtime setting."""

    def test_key_matches_the_switch_module(self) -> None:
        """The catalog literal and the switch module agree on the key."""
        assert DISABLED_NODE_KINDS_KEY == DISABLED_NODE_KINDS_SETTING_KEY

    def test_entry_exists(self) -> None:
        assert DISABLED_NODE_KINDS_KEY in _catalog_by_key

    def test_entry_metadata(self) -> None:
        """Category, value type, default and group follow the slice 3 contract."""
        defn = _catalog_by_key[DISABLED_NODE_KINDS_KEY]
        assert defn.category is SettingCategory.WORKFLOW_EXECUTION
        assert defn.value_type is SettingValueType.JSON
        assert defn.default_value == []
        assert defn.group == WorkflowEngineGroup.NODE_KINDS
        assert defn.requires_restart is False

    def test_allowed_items_are_exactly_the_switchable_kinds(self) -> None:
        """The schema stays in sync with the node-kind registry."""
        defn = _catalog_by_key[DISABLED_NODE_KINDS_KEY]
        assert defn.validation_schema is not None
        allowed = set(defn.validation_schema["allowed_items"])
        assert allowed == {info.kind for info in NODE_KINDS if is_kind_switchable(info.kind)}

    def test_flow_control_kinds_are_not_allowed(self) -> None:
        """Flow control kinds can never be written into the setting."""
        assert "condition" not in SWITCHABLE_NODE_KINDS

    def test_schema_is_compatible_with_value_type(self) -> None:
        defn = _catalog_by_key[DISABLED_NODE_KINDS_KEY]
        assert defn.validation_schema is not None
        check_schema_compatibility(defn.key, defn.value_type, defn.validation_schema)

    def test_default_passes_validation(self) -> None:
        defn = _catalog_by_key[DISABLED_NODE_KINDS_KEY]
        validate_setting_value(
            key=defn.key,
            value=defn.default_value,
            value_type=defn.value_type,
            validation_schema=defn.validation_schema,
        )


class TestAllowedItemsConstraint:
    """The ``allowed_items`` constraint for list-valued JSON settings."""

    _SCHEMA: ClassVar[dict[str, Any]] = {"allowed_items": ["script", "http_request"]}

    def _validate(self, value: object) -> None:
        validate_setting_value(
            key="workflows.disabled_node_kinds",
            value=value,
            value_type=SettingValueType.JSON,
            validation_schema=self._SCHEMA,
        )

    @pytest.mark.parametrize("value", [[], ["script"], ["script", "http_request"]])
    def test_accepts_allowed_members(self, value: list[str]) -> None:
        self._validate(value)

    def test_rejects_unknown_member(self) -> None:
        with pytest.raises(SettingValidationError, match="unsupported item"):
            self._validate(["script", "not_a_kind"])

    def test_rejects_non_list(self) -> None:
        with pytest.raises(SettingValidationError, match="must be a JSON list"):
            self._validate("script")

    def test_error_lists_the_allowed_values(self) -> None:
        with pytest.raises(SettingValidationError) as exc_info:
            self._validate(["condition"])
        assert "http_request" in str(exc_info.value)

    @pytest.mark.parametrize(
        "value_type",
        [SettingValueType.STRING, SettingValueType.INTEGER, SettingValueType.BOOLEAN],
    )
    def test_constraint_requires_json_value_type(self, value_type: SettingValueType) -> None:
        with pytest.raises(SettingValidationError, match="only valid for JSON"):
            check_schema_compatibility("some.key", value_type, self._SCHEMA)
