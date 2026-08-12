"""Tests for newly added settings catalog entries (AAP-70887)."""

import pytest

from syntara.settings.catalog import SETTINGS_CATALOG, SettingDefinition
from syntara.settings.models.runtime_setting import SettingCategory, SettingValueType

_NEW_KEYS = [
    "document_conversion.timeout_seconds",
    "document_conversion.overwrite_existing",
    "workflow_engine.max_loop_iterations",
    "workflow_engine.script_timeout_seconds",
    "workflow_engine.agentic_timeout_seconds",
    "workflow_engine.max_prompt_length",
    "agentic.max_completion_tokens",
    "workflow_engine.script_max_output_kb",
]

_catalog_by_key = {d.key: d for d in SETTINGS_CATALOG}


class TestNewCatalogEntries:
    """Verify new settings are present with correct metadata."""

    @pytest.mark.parametrize("key", _NEW_KEYS)
    def test_key_exists_in_catalog(self, key: str) -> None:
        assert key in _catalog_by_key, f"Missing catalog entry: {key}"

    @pytest.mark.parametrize("key", _NEW_KEYS)
    def test_entries_are_setting_definitions(self, key: str) -> None:
        assert isinstance(_catalog_by_key[key], SettingDefinition)

    def test_document_conversion_timeout(self) -> None:
        d = _catalog_by_key["document_conversion.timeout_seconds"]
        assert d.category == SettingCategory.APPLICATION
        assert d.value_type == SettingValueType.INTEGER
        assert d.default_value == 30
        assert d.validation_schema == {"min": 1, "max": 300}

    def test_document_conversion_overwrite(self) -> None:
        d = _catalog_by_key["document_conversion.overwrite_existing"]
        assert d.category == SettingCategory.APPLICATION
        assert d.value_type == SettingValueType.BOOLEAN
        assert d.default_value is False

    def test_no_new_settings_require_restart(self) -> None:
        for key in _NEW_KEYS:
            d = _catalog_by_key[key]
            assert d.requires_restart is False, f"{key} should not require restart"

    def test_agentic_max_completion_tokens(self) -> None:
        d = _catalog_by_key["agentic.max_completion_tokens"]
        assert d.category == SettingCategory.AI_LLM
        assert d.value_type == SettingValueType.INTEGER
        assert d.default_value == 0

    def test_script_max_output_kb(self) -> None:
        d = _catalog_by_key["workflow_engine.script_max_output_kb"]
        assert d.category == SettingCategory.WORKFLOW_EXECUTION
        assert d.value_type == SettingValueType.INTEGER
        assert d.default_value == 1024
        assert d.validation_schema == {"min": 256, "max": 2048}

    def test_workflow_settings_have_min_constraint(self) -> None:
        keys = [
            "workflow_engine.max_loop_iterations",
            "workflow_engine.script_timeout_seconds",
            "workflow_engine.agentic_timeout_seconds",
            "workflow_engine.max_prompt_length",
            "workflow_engine.script_max_output_kb",
        ]
        for key in keys:
            d = _catalog_by_key[key]
            assert d.validation_schema is not None
            assert d.validation_schema.get("min") is not None, f"{key} missing min constraint"

    def test_task_agent_system_prompt(self) -> None:
        d = _catalog_by_key["agentic.task_agent_system_prompt"]
        assert d.category == SettingCategory.AI_LLM
        assert d.value_type == SettingValueType.STRING
        assert isinstance(d.default_value, str)
        assert "{product_name}" in d.default_value
        assert d.validation_schema == {"pattern": "\\S[\\s\\S]{0,1999}"}

    def test_removed_settings_not_in_catalog(self) -> None:
        removed = [
            "retriever.llm_model",
            "workflow_engine.api_timeout_seconds",
            "workflow_engine.max_duration_hours",
            "workflow_engine.max_duration_minutes",
            "workflow_engine.max_duration_seconds",
            "workflow_engine.max_input_value_length",
            "workflow_engine.max_total_input_size",
        ]
        for key in removed:
            assert key not in _catalog_by_key, f"{key} should have been removed from catalog"
