"""Verify the script_nodes_enabled setting is registered in the catalog."""

from syntara.settings.catalog import SETTINGS_CATALOG


class TestScriptNodesEnabledSetting:
    """Test the workflow_engine.script_nodes_enabled setting."""

    def test_setting_exists_in_catalog(self) -> None:
        keys = {s.key for s in SETTINGS_CATALOG}
        assert "workflow_engine.script_nodes_enabled" in keys

    def test_setting_defaults_to_true(self) -> None:
        setting = next(s for s in SETTINGS_CATALOG if s.key == "workflow_engine.script_nodes_enabled")
        assert setting.default_value is True

    def test_setting_is_boolean_type(self) -> None:
        from syntara.settings.models.runtime_setting import SettingValueType

        setting = next(s for s in SETTINGS_CATALOG if s.key == "workflow_engine.script_nodes_enabled")
        assert setting.value_type == SettingValueType.BOOLEAN
