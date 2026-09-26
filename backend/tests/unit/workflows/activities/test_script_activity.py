"""Unit tests for execute_script_activity — Temporal gate, validation, and feature flags."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from execution_plane.script_executor import execute_script
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.workflows.workflow_engine.activities.ep.ep_dispatch_activity import execute_script_activity

ACTIVITY_INFO_PATH = "syntara.workflows.workflow_engine.activities.ep.ep_dispatch_activity.activity.info"


@pytest.fixture(autouse=True)
def _mock_activity_context() -> Generator[MagicMock, None, None]:
    """Auto-mock activity.info() and activity.heartbeat() so tests can run outside a Temporal worker.

    Sets attempt=1 by default; individual tests can override via
    ``mock_activity_info`` fixture.
    """
    mock_info = MagicMock()
    mock_info.attempt = 1
    with patch(ACTIVITY_INFO_PATH, return_value=mock_info) as m, patch("temporalio.activity.heartbeat"):
        yield m


@pytest.fixture
def mock_activity_info(_mock_activity_context: MagicMock) -> MagicMock:
    """Expose the mock so tests can customise attempt number etc."""
    return _mock_activity_context


class TestScriptEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_script(self) -> None:
        input_config = {"language": "bash", "code": ":"}
        result = await execute_script(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"] == ""

    @pytest.mark.asyncio
    async def test_script_with_only_whitespace(self) -> None:
        input_config = {"language": "bash", "code": "   \n\n   "}
        result = await execute_script(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"].strip() == ""

    @pytest.mark.asyncio
    async def test_script_with_only_comments(self) -> None:
        script = """
# This is a comment
# Another comment
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"] == ""

    @pytest.mark.asyncio
    async def test_very_long_output(self) -> None:
        script = """
for i in {1..100}; do
    echo "Line $i"
done
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Line 1" in output["stdout"]
        assert "Line 100" in output["stdout"]

    @pytest.mark.asyncio
    async def test_unicode_in_output(self) -> None:
        input_config = {"language": "bash", "code": 'echo "Hello 世界"'}
        result = await execute_script(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "世界" in output["stdout"]

    @pytest.mark.asyncio
    async def test_unsupported_language_raises_config_error(self) -> None:
        """Unsupported language is caught by Pydantic validation in execute_script_activity."""
        input_config = {"language": "ruby", "code": "puts 'hello'"}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ConfigError"


class TestPydanticConfigValidation:
    """Test that ScriptExecutorParameters.model_validate() is enforced."""

    @pytest.mark.asyncio
    async def test_empty_code_raises_config_error(self) -> None:
        """Empty code string violates min_length=1 and raises ApplicationError."""
        input_config = {"language": "bash", "code": ""}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_invalid_language_raises_config_error(self) -> None:
        """Non-enum language value is rejected by Pydantic."""
        input_config = {"language": "ruby", "code": "puts 'hello'"}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_missing_code_field_raises_config_error(self) -> None:
        """Missing required 'code' field is rejected by Pydantic."""
        input_config = {"language": "bash"}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_missing_language_field_raises_config_error(self) -> None:
        """Missing required 'language' field is rejected by Pydantic."""
        input_config = {"code": "echo hello"}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_non_string_environment_values_coerced(self) -> None:
        """Environment with non-string values are coerced to strings."""
        input_config = {
            "language": "bash",
            "code": "echo $KEY",
            "environment": {"KEY": 123},
        }
        result = await execute_script(input_config, None)
        assert result["output"]["return_code"] == 0
        assert result["output"]["stdout"].strip() == "123"

    @pytest.mark.asyncio
    async def test_valid_config_at_boundary_timeout_1(self) -> None:
        """Timeout=1 is the minimum valid value."""
        input_config = {"language": "bash", "code": "echo ok", "timeout": 1}
        result = await execute_script(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0

    @pytest.mark.asyncio
    async def test_valid_config_at_boundary_timeout_3600(self) -> None:
        """Timeout=3600 is the maximum valid value."""
        input_config = {"language": "bash", "code": "echo ok", "timeout": 3600}
        result = await execute_script(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0

    @pytest.mark.asyncio
    async def test_completely_empty_config_raises_config_error(self) -> None:
        """Empty dict is rejected by Pydantic (missing required fields)."""
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity({}, None)
        assert exc_info.value.type == "ConfigError"


class TestScriptNodesGate:
    """Test the APP_SCRIPT_NODES_ENABLED script node gate."""

    @pytest.mark.asyncio
    async def test_disabled_raises_application_error(self) -> None:
        """When script_nodes_enabled is False, the activity fails immediately."""
        settings = get_settings()
        object.__setattr__(settings, "script_nodes_enabled", False)
        try:
            with pytest.raises(ApplicationError) as exc_info:
                await execute_script_activity({"language": "bash", "code": "echo hi"}, None)

            assert exc_info.value.non_retryable is True
            assert exc_info.value.type == "ScriptNodeDisabled"
        finally:
            object.__setattr__(settings, "script_nodes_enabled", True)

    @pytest.mark.asyncio
    async def test_disabled_error_message_is_opaque(self) -> None:
        """Error message must not reference the setting name."""
        settings = get_settings()
        object.__setattr__(settings, "script_nodes_enabled", False)
        try:
            with pytest.raises(ApplicationError) as exc_info:
                await execute_script_activity({"language": "bash", "code": "echo hi"}, None)

            message = str(exc_info.value)
            assert "APP_SCRIPT_NODES_ENABLED" not in message
            assert "script_nodes_enabled" not in message
            assert "setting" not in message.lower()
            assert "Script node execution is not enabled" in message
        finally:
            object.__setattr__(settings, "script_nodes_enabled", True)

    @pytest.mark.asyncio
    async def test_disabled_does_not_execute_script(self) -> None:
        """When disabled, no subprocess should be spawned."""
        settings = get_settings()
        object.__setattr__(settings, "script_nodes_enabled", False)
        try:
            with (
                patch(
                    "execution_plane.script_executor.asyncio.create_subprocess_exec",
                ) as mock_exec,
                pytest.raises(ApplicationError),
            ):
                await execute_script_activity({"language": "bash", "code": "echo hi"}, None)

            mock_exec.assert_not_called()
        finally:
            object.__setattr__(settings, "script_nodes_enabled", True)

    @pytest.mark.asyncio
    async def test_enabled_executes_normally(self) -> None:
        """When script_nodes_enabled is True (autouse fixture), scripts execute."""
        result = await execute_script({"language": "bash", "code": "echo gate-open"}, None)
        assert result["output"]["return_code"] == 0
        assert "gate-open" in result["output"]["stdout"]
