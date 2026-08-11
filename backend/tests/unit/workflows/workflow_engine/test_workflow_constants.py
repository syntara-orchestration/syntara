"""Unit tests for workflow engine constants module.

Tests that static constants (infrastructure/operational settings) are
loaded from Pydantic BaseSettings / environment variables. Runtime-
configurable settings are read from the settings cache by activities
and are NOT defined in constants.py.
"""

import importlib
import sys
from collections.abc import Generator

import pytest

from syntara.core.config.base import get_settings


@pytest.fixture
def isolated_constants() -> Generator[None, None, None]:
    """Reload constants module for each test to ensure isolation."""
    module_name = "syntara.workflows.workflow_engine.constants"
    if module_name in sys.modules:
        del sys.modules[module_name]
    get_settings.cache_clear()
    yield
    if module_name in sys.modules:
        del sys.modules[module_name]
    get_settings.cache_clear()


@pytest.mark.usefixtures("isolated_constants")
class TestConstantsModuleLoading:
    """Tests for constants module loading."""

    def test_constants_module_imports_successfully(self) -> None:
        from syntara.workflows.workflow_engine import constants

        assert constants is not None

    def test_all_expected_constants_are_defined(self) -> None:
        from syntara.workflows.workflow_engine import constants

        expected_constants = [
            "DEFAULT_ACTIVITY_TIMEOUT_SECONDS",
            "AGENT_ORCHESTRATOR_BASE_URL",
            "SCRIPT_CLEANUP_TERMINATE_TIMEOUT",
            "SCRIPT_CLEANUP_KILL_TIMEOUT",
            "MAX_ENV_VAR_LENGTH",
        ]

        for const_name in expected_constants:
            assert hasattr(constants, const_name), f"Missing constant: {const_name}"

    def test_static_constants_loaded_from_settings(self) -> None:
        from syntara.workflows.workflow_engine import constants

        settings = get_settings()
        assert str(settings.agent_orchestrator_base_url) == constants.AGENT_ORCHESTRATOR_BASE_URL
        assert settings.script_cleanup_terminate_timeout == constants.SCRIPT_CLEANUP_TERMINATE_TIMEOUT
        assert settings.script_cleanup_kill_timeout == constants.SCRIPT_CLEANUP_KILL_TIMEOUT
        assert settings.max_env_var_length == constants.MAX_ENV_VAR_LENGTH

    def test_static_constants_respect_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_AGENT_ORCHESTRATOR_BASE_URL", "http://custom.example.com/api/v1")
        monkeypatch.setenv("APP_SCRIPT_CLEANUP_TERMINATE_TIMEOUT", "2.0")
        monkeypatch.setenv("APP_SCRIPT_CLEANUP_KILL_TIMEOUT", "1.0")
        monkeypatch.setenv("APP_MAX_ENV_VAR_LENGTH", "65536")

        import syntara.workflows.workflow_engine.constants as constants_module

        constants = importlib.reload(constants_module)

        assert constants.AGENT_ORCHESTRATOR_BASE_URL == "http://custom.example.com/api/v1"
        assert constants.SCRIPT_CLEANUP_TERMINATE_TIMEOUT == 2.0
        assert constants.SCRIPT_CLEANUP_KILL_TIMEOUT == 1.0
        assert constants.MAX_ENV_VAR_LENGTH == 65536

    def test_runtime_settings_not_in_constants(self) -> None:
        """Runtime-configurable settings should NOT be in constants."""
        from syntara.workflows.workflow_engine import constants

        assert not hasattr(constants, "MAX_LOOP_ITERATIONS")
        assert not hasattr(constants, "DEFAULT_SCRIPT_TIMEOUT_SECONDS")
        assert not hasattr(constants, "DEFAULT_AGENTIC_TIMEOUT_SECONDS")
        assert not hasattr(constants, "API_TIMEOUT_SECONDS")
        assert not hasattr(constants, "MAX_PROMPT_LENGTH")
