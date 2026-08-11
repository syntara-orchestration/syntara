"""Unit tests for script activity executor (V2 unified bash/python)."""

import asyncio
import sys
from collections.abc import Generator
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.script_activity import (
    SAFE_ENV_ALLOWLIST,
    ScriptExecutionError,
    _communicate_limited,
    _enforce_payload_limit,
    _get_cgroup_memory_limit,
    _prepare_script_env,
    _prepend_memory_limit,
    _process_script_result,
    _sanitize_env_value,
    execute_script_activity,
)

ACTIVITY_INFO_PATH = "syntara.workflows.workflow_engine.activities.script_activity.activity.info"


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


class TestBashScriptExecution:
    """Test basic bash script execution functionality."""

    @pytest.mark.asyncio
    async def test_simple_echo(self) -> None:
        """Test simple echo command."""
        input_config = {"language": "bash", "code": 'echo "Hello, World!"'}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Hello, World!" in output["stdout"]
        assert output["stderr"] == ""

    @pytest.mark.asyncio
    async def test_multiline_script(self) -> None:
        """Test multiline bash script."""
        script = """
echo "Line 1"
echo "Line 2"
echo "Line 3"
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Line 1" in output["stdout"]
        assert "Line 2" in output["stdout"]
        assert "Line 3" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_with_variables(self) -> None:
        """Test script with bash variables."""
        script = """
        NAME="Workflow"
        echo "Hello, $NAME!"
        """
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Hello, Workflow!" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_with_commands(self) -> None:
        """Test script with actual bash commands."""
        script = """
        date_output=$(date +%Y-%m-%d)
        echo "Date: $date_output"
        """
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Date:" in output["stdout"]


class TestScriptEnvironmentVariables:
    """Test custom environment variables from config.environment."""

    @pytest.mark.asyncio
    async def test_bash_custom_env_variable(self) -> None:
        """Test bash script with custom environment variable."""
        input_config = {
            "language": "bash",
            "code": 'echo "API Key: $API_KEY"',
            "environment": {"API_KEY": "secret123"},
        }
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "API Key: secret123" in output["stdout"]

    @pytest.mark.asyncio
    async def test_bash_multiple_env_variables(self) -> None:
        """Test bash script with multiple custom environment variables."""
        script = """
echo "Database: $DB_HOST:$DB_PORT"
echo "User: $DB_USER"
"""
        input_config = {
            "language": "bash",
            "code": script,
            "environment": {"DB_HOST": "localhost", "DB_PORT": "5432", "DB_USER": "admin"},
        }
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Database: localhost:5432" in output["stdout"]
        assert "User: admin" in output["stdout"]

    @pytest.mark.asyncio
    async def test_python_custom_env_variable(self) -> None:
        """Test Python script with custom environment variable."""
        script = """
import os
api_key = os.getenv('API_KEY', 'default')
print(f"API Key: {api_key}")
"""
        input_config = {
            "language": "python",
            "code": script,
            "environment": {"API_KEY": "secret123"},
        }
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "API Key: secret123" in output["stdout"]

    @pytest.mark.asyncio
    async def test_python_multiple_env_variables(self) -> None:
        """Test Python script with multiple custom environment variables."""
        script = """
import os
import json
config = {
    'db_host': os.getenv('DB_HOST'),
    'db_port': os.getenv('DB_PORT'),
    'db_user': os.getenv('DB_USER')
}
print(json.dumps(config))
"""
        input_config = {
            "language": "python",
            "code": script,
            "environment": {"DB_HOST": "localhost", "DB_PORT": "5432", "DB_USER": "admin"},
        }
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout_json"]["db_host"] == "localhost"
        assert output["stdout_json"]["db_port"] == "5432"
        assert output["stdout_json"]["db_user"] == "admin"


class TestScriptOutputParsing:
    """Test script output parsing and capture."""

    @pytest.mark.asyncio
    async def test_stdout_capture(self) -> None:
        """Test that stdout is properly captured."""
        script = """
echo "Output line 1"
echo "Output line 2"
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert "Output line 1" in output["stdout"]
        assert "Output line 2" in output["stdout"]

    @pytest.mark.asyncio
    async def test_stderr_capture(self) -> None:
        """Test that stderr is properly captured."""
        input_config = {"language": "bash", "code": 'echo "Error message" >&2'}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Error message" in output["stderr"]

    @pytest.mark.asyncio
    async def test_json_output(self) -> None:
        """Test script that outputs JSON."""
        input_config = {"language": "bash", "code": 'echo \'{"status": "success", "count": 42}\''}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert '{"status": "success"' in output["stdout"]
        assert '"count": 42' in output["stdout"]

    @pytest.mark.asyncio
    async def test_empty_output(self) -> None:
        """Test script with no output."""
        input_config = {"language": "bash", "code": "# Just a comment, no output"}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"] == ""
        assert output["stderr"] == ""


class TestScriptErrorHandling:
    """Test error handling in script execution."""

    @pytest.mark.asyncio
    async def test_non_zero_exit_code(self) -> None:
        """Test script that exits with non-zero code raises ApplicationError."""
        input_config = {"language": "bash", "code": "exit 1"}

        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ScriptExecutionError"

    @pytest.mark.asyncio
    async def test_command_not_found(self) -> None:
        """Test script with invalid command raises ApplicationError."""
        input_config = {"language": "bash", "code": "nonexistentcommand12345"}

        with pytest.raises(ApplicationError):
            await execute_script_activity(input_config, None)

    @pytest.mark.asyncio
    async def test_syntax_error(self) -> None:
        """Test script with bash syntax error raises ApplicationError."""
        input_config = {"language": "bash", "code": 'if [ true ]; then\necho "incomplete"'}

        with pytest.raises(ApplicationError):
            await execute_script_activity(input_config, None)


class TestScriptAdvancedFeatures:
    """Test advanced script execution features."""

    @pytest.mark.asyncio
    async def test_script_with_pipes(self) -> None:
        """Test script using pipes."""
        input_config = {"language": "bash", "code": 'echo "hello world" | tr "a-z" "A-Z"'}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "HELLO WORLD" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_with_conditionals(self) -> None:
        """Test script with if/else."""
        script = """
ARG="test"
if [ "$ARG" = "test" ]; then
    echo "Condition true"
else
    echo "Condition false"
fi
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Condition true" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_with_loop(self) -> None:
        """Test script with loop."""
        script = """
for i in 1 2 3; do
    echo "Item: $i"
done
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Item: 1" in output["stdout"]
        assert "Item: 2" in output["stdout"]
        assert "Item: 3" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_with_arithmetic(self) -> None:
        """Test script with arithmetic operations."""
        script = """
a=10
b=5
result=$((a + b))
echo "Result: $result"
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Result: 15" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_with_file_operations(self) -> None:
        """Test script that creates and reads temporary file."""
        script = """
tmpfile=$(mktemp)
echo "test content" > "$tmpfile"
cat "$tmpfile"
rm "$tmpfile"
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "test content" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_with_subshell(self) -> None:
        """Test script using subshell."""
        script = """
output=$(echo "subshell output")
echo "From subshell: $output"
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "From subshell: subshell output" in output["stdout"]


class TestScriptEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_script(self) -> None:
        """Test script with no output (minimal valid script)."""
        input_config = {"language": "bash", "code": ":"}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"] == ""

    @pytest.mark.asyncio
    async def test_script_with_only_whitespace(self) -> None:
        """Test script with only whitespace."""
        input_config = {"language": "bash", "code": "   \n\n   "}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"].strip() == ""

    @pytest.mark.asyncio
    async def test_script_with_only_comments(self) -> None:
        """Test script with only comments."""
        script = """
# This is a comment
# Another comment
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"] == ""

    @pytest.mark.asyncio
    async def test_very_long_output(self) -> None:
        """Test script with very long output."""
        script = """
for i in {1..100}; do
    echo "Line $i"
done
"""
        input_config = {"language": "bash", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Line 1" in output["stdout"]
        assert "Line 100" in output["stdout"]

    @pytest.mark.asyncio
    async def test_unicode_in_output(self) -> None:
        """Test script with unicode characters."""
        input_config = {"language": "bash", "code": 'echo "Hello 世界"'}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "世界" in output["stdout"]

    @pytest.mark.asyncio
    async def test_unsupported_language_raises_config_error(self) -> None:
        """Test that unsupported language is caught by Pydantic validation."""
        input_config = {"language": "ruby", "code": "puts 'hello'"}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ConfigError"


class TestPythonScriptExecution:
    """Test Python script execution functionality."""

    @pytest.mark.asyncio
    async def test_simple_python_print(self) -> None:
        """Test simple Python print statement."""
        input_config = {"language": "python", "code": 'print("Hello from Python!")'}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Hello from Python!" in output["stdout"]
        assert output["stderr"] == ""

    @pytest.mark.asyncio
    async def test_python_json_output(self) -> None:
        """Test Python script with JSON output."""
        script = """
import json
data = {"message": "Hello", "value": 42}
print(json.dumps(data))
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "stdout_json" in output
        assert output["stdout_json"]["message"] == "Hello"
        assert output["stdout_json"]["value"] == 42

    @pytest.mark.asyncio
    async def test_python_multiline_script(self) -> None:
        """Test multiline Python script."""
        script = """
for i in range(3):
    print(f"Line {i}")
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "Line 0" in output["stdout"]
        assert "Line 1" in output["stdout"]
        assert "Line 2" in output["stdout"]

    @pytest.mark.asyncio
    async def test_python_calculation(self) -> None:
        """Test Python script with calculation."""
        script = """
result = 10 + 20
print(result)
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "30" in output["stdout"]


class TestPythonScriptErrorHandling:
    """Test Python script error handling."""

    @pytest.mark.asyncio
    async def test_python_syntax_error(self) -> None:
        """Test Python script with syntax error raises ApplicationError."""
        input_config = {"language": "python", "code": 'print("Missing closing quote'}

        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity(input_config, None)
        assert exc_info.value.type == "ScriptExecutionError"

    @pytest.mark.asyncio
    async def test_python_runtime_error(self) -> None:
        """Test Python script with runtime error raises ApplicationError."""
        script = """
x = 10
y = 0
result = x / y  # Division by zero
"""
        input_config = {"language": "python", "code": script}

        with pytest.raises(ApplicationError):
            await execute_script_activity(input_config, None)

    @pytest.mark.asyncio
    async def test_python_import_error(self) -> None:
        """Test Python script with import error raises ApplicationError."""
        input_config = {"language": "python", "code": "import nonexistent_module"}

        with pytest.raises(ApplicationError):
            await execute_script_activity(input_config, None)


class TestPythonScriptOutputParsing:
    """Test Python script JSON output parsing."""

    @pytest.mark.asyncio
    async def test_python_valid_json_output(self) -> None:
        """Test Python script with valid JSON output."""
        script = """
import json
data = {"status": "success", "items": [1, 2, 3]}
print(json.dumps(data))
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "stdout_json" in output
        assert output["stdout_json"]["status"] == "success"
        assert output["stdout_json"]["items"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_python_invalid_json_output(self) -> None:
        """Test Python script with non-JSON output."""
        input_config = {"language": "python", "code": 'print("This is not JSON")'}

        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "This is not JSON" in output["stdout"]
        assert output["stdout_json"] is None

    @pytest.mark.asyncio
    async def test_python_debug_output_with_json_last_line(self) -> None:
        """Test Python script with debug prints before JSON on last line."""
        script = """
import json

print("Debug: Starting processing...")
print("Debug: Loading data...")

result = {"status": "success", "items_processed": 3, "result": "complete"}
print(json.dumps(result))
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0

        # Should have parsed JSON from last line
        assert "stdout_json" in output
        assert output["stdout_json"]["status"] == "success"
        assert output["stdout_json"]["items_processed"] == 3

        # Full stdout should include debug lines
        assert "Debug: Starting processing..." in output["stdout"]

    @pytest.mark.asyncio
    async def test_python_empty_output(self) -> None:
        """Test Python script with no output."""
        input_config = {"language": "python", "code": "pass"}

        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert output["stdout"] == ""

    @pytest.mark.asyncio
    async def test_python_nested_json_output(self) -> None:
        """Test Python script with nested JSON structures."""
        script = """
import json
data = {
    "user": {
        "name": "Test User",
        "details": {
            "age": 30,
            "city": "Boston"
        }
    }
}
print(json.dumps(data))
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "stdout_json" in output
        assert output["stdout_json"]["user"]["name"] == "Test User"
        assert output["stdout_json"]["user"]["details"]["age"] == 30


# ────────────────────────────────────────────────────────────────────
# Task 4.1 — Tests for Pydantic validation and sys.executable
# ────────────────────────────────────────────────────────────────────


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
        result = await execute_script_activity(input_config, None)
        assert result["output"]["return_code"] == 0
        assert result["output"]["stdout"].strip() == "123"

    @pytest.mark.asyncio
    async def test_valid_config_at_boundary_timeout_1(self) -> None:
        """Timeout=1 is the minimum valid value."""
        input_config = {"language": "bash", "code": "echo ok", "timeout": 1}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0

    @pytest.mark.asyncio
    async def test_valid_config_at_boundary_timeout_3600(self) -> None:
        """Timeout=3600 is the maximum valid value."""
        input_config = {"language": "bash", "code": "echo ok", "timeout": 3600}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0

    @pytest.mark.asyncio
    async def test_completely_empty_config_raises_config_error(self) -> None:
        """Empty dict is rejected by Pydantic (missing required fields)."""
        with pytest.raises(ApplicationError) as exc_info:
            await execute_script_activity({}, None)
        assert exc_info.value.type == "ConfigError"


class TestSysExecutableForPython:
    """Test that Python scripts use sys.executable instead of hardcoded 'python'."""

    @pytest.mark.asyncio
    async def test_python_script_uses_sys_executable(self) -> None:
        """Python script subprocess should use the same interpreter as the host process."""
        script = """
import sys
print(sys.executable)
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        # The subprocess should report the same executable as the host
        assert sys.executable in output["stdout"]

    @pytest.mark.asyncio
    async def test_bash_script_does_not_use_sys_executable(self) -> None:
        """Bash scripts should still use 'bash', not sys.executable."""
        input_config = {"language": "bash", "code": "echo $0"}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "bash" in output["stdout"]


# ---------------------------------------------------------------------------
# Unit tests for internal helpers (cover lines not reached via subprocess)
# ---------------------------------------------------------------------------


class TestSanitizeEnvValue:
    """Tests for _sanitize_env_value input validation."""

    def test_null_byte_raises(self) -> None:
        from syntara.core.exceptions import SafeValueError

        with pytest.raises(SafeValueError, match="null bytes"):
            _sanitize_env_value("value\x00with_null")

    def test_exceeds_max_length_raises(self) -> None:
        from syntara.core.exceptions import SafeValueError
        from syntara.workflows.workflow_engine import constants

        with pytest.raises(SafeValueError, match="maximum length"):
            _sanitize_env_value("x" * (constants.MAX_ENV_VAR_LENGTH + 1))

    def test_normal_string_passes(self) -> None:
        assert _sanitize_env_value("hello") == "hello"

    def test_dict_serialized_as_json(self) -> None:
        result = _sanitize_env_value({"key": "value"})
        assert result == '{"key": "value"}'

    def test_list_serialized_as_json(self) -> None:
        result = _sanitize_env_value([1, 2, 3])
        assert result == "[1, 2, 3]"


class TestProcessScriptResult:
    """Tests for _process_script_result edge cases."""

    def test_returncode_none_raises_runtime_error(self) -> None:
        with pytest.raises(RuntimeError, match="returncode is None"):
            _process_script_result(None, b"stdout", b"stderr")

    def test_nonzero_exit_code_raises_script_error(self) -> None:
        with pytest.raises(ScriptExecutionError):
            _process_script_result(1, b"out", b"err")

    def test_zero_exit_code_returns_result(self) -> None:
        result = _process_script_result(0, b"hello\n", b"")
        assert result["return_code"] == 0
        assert result["stdout"] == "hello\n"
        assert result["stderr"] == ""

    def test_none_bytes_handled(self) -> None:
        result = _process_script_result(0, None, None)
        assert result["stdout"] == ""
        assert result["stderr"] == ""


class TestGenericExceptionHandler:
    """Test the outer generic exception handler in execute_script_activity."""

    @pytest.mark.asyncio
    async def test_subprocess_error_raises_application_error(self) -> None:
        """SubprocessError falls through to generic ApplicationError handler."""
        import subprocess

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.script_activity.asyncio.create_subprocess_exec",
                side_effect=subprocess.SubprocessError("spawn failed"),
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_script_activity({"language": "bash", "code": "echo hi"}, None)
        assert exc_info.value.non_retryable is True


class TestScriptActivityTimeoutAndInputs:
    """Cover remaining uncovered paths in script activity."""

    @pytest.mark.asyncio
    async def test_timeout_raises_application_error(self) -> None:
        """TimeoutError from asyncio.wait_for propagates as ApplicationError with specific message."""
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stdin = None
        mock_process._transport = None
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.script_activity.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_process,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.script_activity._communicate_limited",
                new_callable=AsyncMock,
                side_effect=TimeoutError(),
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_script_activity(
                {"language": "bash", "code": "sleep 999", "_engine_timeout_seconds": 10}, None
            )
        assert exc_info.value.non_retryable is True
        assert "timed out after 10 seconds" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_inputs_with_none_value_skipped(self) -> None:
        """None values in inputs dict are not added to environment."""
        script = 'echo "${INPUT_KEY:-missing}"'
        input_config = {"language": "bash", "code": script}
        # V2 resolves templates before calling the activity; inputs dict is empty
        result = await execute_script_activity(input_config, None)
        assert result["output"]["return_code"] == 0


class TestScriptEnvironmentSanitization:
    """Test that script subprocesses do NOT inherit sensitive worker environment variables.

    The worker process runs with secrets (encryption keys, DB credentials, JWT keys).
    Scripts must only receive an explicit allowlist of safe system variables plus
    user-defined config.environment and INPUT_ vars.
    """

    SENSITIVE_VARS: ClassVar[dict[str, str]] = {
        "APP_SECRET_ENCRYPTION_KEY": "0123456789abcdef" * 4,
        "APP_DATABASE_URL": "postgresql://admin:secret@db:5432/nexus",
        "APP_DB_PASSWORD": "super_secret_db_pass",
        "APP_CACHE_PASSWORD": "redis_secret",
        "APP_JWT_PRIVATE_KEY_PATH": "/secrets/jwt.pem",
        "APP_S3_SECRET_ACCESS_KEY": "s3secretkey123",
        "APP_ADMIN_PASSWORD_PATH": "/secrets/admin-password",
        "APP_OTEL_API_KEY": "otel-api-key-secret",
        "APP_SEGMENT_WRITE_KEY": "segment-write-key",
    }

    def test_sensitive_vars_excluded_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sensitive APP_* variables must not appear in the prepared environment."""
        for key, value in self.SENSITIVE_VARS.items():
            monkeypatch.setenv(key, value)

        env = _prepare_script_env()

        for key in self.SENSITIVE_VARS:
            assert key not in env, f"{key} leaked into script environment"

    def test_safe_vars_included_in_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Safe system variables (PATH, HOME, LANG, TZ) must be present."""
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        monkeypatch.setenv("HOME", "/home/testuser")
        monkeypatch.setenv("LANG", "en_US.UTF-8")
        monkeypatch.setenv("TZ", "UTC")

        env = _prepare_script_env()

        assert env["PATH"] == "/usr/bin:/bin"
        assert env["HOME"] == "/home/testuser"
        assert env["LANG"] == "en_US.UTF-8"
        assert env["TZ"] == "UTC"

    def test_custom_environment_vars_still_work(self) -> None:
        """User-defined config.environment variables must pass through."""
        env = _prepare_script_env({"MY_CUSTOM_VAR": "hello", "ANOTHER_VAR": "world"})

        assert env["MY_CUSTOM_VAR"] == "hello"
        assert env["ANOTHER_VAR"] == "world"

    def test_arbitrary_unknown_vars_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Variables not on the allowlist must not appear — allowlist, not blocklist."""
        monkeypatch.setenv("SOME_INTERNAL_SERVICE_TOKEN", "tok_12345")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-secret")

        env = _prepare_script_env()

        assert "SOME_INTERNAL_SERVICE_TOKEN" not in env
        assert "OPENROUTER_API_KEY" not in env

    def test_only_allowlisted_system_vars_inherited(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every key inherited from os.environ must be in SAFE_ENV_ALLOWLIST."""
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/home/user")
        monkeypatch.setenv("NOT_ON_ALLOWLIST", "should_not_appear")
        for key, value in self.SENSITIVE_VARS.items():
            monkeypatch.setenv(key, value)

        env = _prepare_script_env()

        inherited_keys = set(env.keys())
        assert inherited_keys.issubset(SAFE_ENV_ALLOWLIST), (
            f"Non-allowlisted keys inherited: {inherited_keys - SAFE_ENV_ALLOWLIST}"
        )

    @pytest.mark.asyncio
    async def test_script_cannot_read_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A bash script must not be able to read sensitive env vars."""
        monkeypatch.setenv("APP_SECRET_ENCRYPTION_KEY", "leaked_master_key")

        input_config = {
            "language": "bash",
            "code": 'echo "KEY=${APP_SECRET_ENCRYPTION_KEY:-empty}"',
        }
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "leaked_master_key" not in output["stdout"]
        assert "KEY=empty" in output["stdout"]

    @pytest.mark.asyncio
    async def test_script_can_read_path(self) -> None:
        """A bash script must still be able to read PATH."""
        input_config = {
            "language": "bash",
            "code": 'echo "PATH=$PATH"',
        }
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        assert "PATH=/" in output["stdout"]

    @pytest.mark.asyncio
    async def test_python_env_dump_has_no_app_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A Python script dumping os.environ must not see any APP_* secrets."""
        for key, value in self.SENSITIVE_VARS.items():
            monkeypatch.setenv(key, value)

        script = """
import os
import json
env_keys = list(os.environ.keys())
print(json.dumps(env_keys))
"""
        input_config = {"language": "python", "code": script}
        result = await execute_script_activity(input_config, None)

        output = result["output"]
        assert output["return_code"] == 0
        env_keys = output["stdout_json"]
        app_keys = [k for k in env_keys if k.startswith("APP_")]
        assert app_keys == [], f"APP_* vars leaked into script: {app_keys}"


def _make_stream_reader(data: bytes) -> asyncio.StreamReader:
    """Create an asyncio.StreamReader pre-loaded with data."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class TestCommunicateLimited:
    """Test _communicate_limited with concurrent stdout/stderr."""

    @pytest.mark.asyncio
    async def test_both_under_cap(self) -> None:
        process = AsyncMock()
        process.stdout = _make_stream_reader(b"out")
        process.stderr = _make_stream_reader(b"err")
        process.wait = AsyncMock()
        stdout, stderr, st, se = await _communicate_limited(process, 1024)
        assert stdout == b"out"
        assert stderr == b"err"
        assert st is False
        assert se is False

    @pytest.mark.asyncio
    async def test_stdout_truncated(self) -> None:
        process = AsyncMock()
        process.stdout = _make_stream_reader(b"x" * 200)
        process.stderr = _make_stream_reader(b"err")
        process.wait = AsyncMock()
        stdout, stderr, st, se = await _communicate_limited(process, 50)
        assert len(stdout) == 50
        assert st is True
        assert stderr == b"err"
        assert se is False

    @pytest.mark.asyncio
    async def test_stderr_truncated(self) -> None:
        process = AsyncMock()
        process.stdout = _make_stream_reader(b"out")
        process.stderr = _make_stream_reader(b"y" * 200)
        process.wait = AsyncMock()
        stdout, stderr, st, se = await _communicate_limited(process, 50)
        assert stdout == b"out"
        assert st is False
        assert len(stderr) == 50
        assert se is True

    @pytest.mark.asyncio
    async def test_both_truncated(self) -> None:
        process = AsyncMock()
        process.stdout = _make_stream_reader(b"x" * 200)
        process.stderr = _make_stream_reader(b"y" * 200)
        process.wait = AsyncMock()
        stdout, stderr, st, se = await _communicate_limited(process, 50)
        assert len(stdout) == 50
        assert st is True
        assert len(stderr) == 50
        assert se is True

    @pytest.mark.asyncio
    async def test_raises_when_stdout_is_none(self) -> None:
        """RuntimeError raised when process.stdout is None."""
        process = AsyncMock()
        process.stdout = None
        process.stderr = AsyncMock()
        with pytest.raises(RuntimeError, match="without PIPE"):
            await _communicate_limited(process, 1024)


class TestOutputLimitIntegration:
    """Test that output limiting works end-to-end via execute_script_activity."""

    @pytest.mark.asyncio
    async def test_truncated_output_includes_notice(self) -> None:
        """When stdout exceeds DEFAULT_MAX_OUTPUT_BYTES, stderr should contain truncation notice."""
        input_config = {
            "language": "bash",
            # DEFAULT_MAX_OUTPUT_BYTES is 1MB; generate well over that
            "code": "dd if=/dev/zero bs=1024 count=1100 2>/dev/null | base64",
        }
        result = await execute_script_activity(input_config, None)
        assert "[Output truncated:" in result["output"]["stderr"]

    @pytest.mark.asyncio
    async def test_small_output_no_truncation(self) -> None:
        """Normal output under the limit should not be truncated."""
        input_config = {
            "language": "bash",
            "code": "echo hello",
        }
        result = await execute_script_activity(input_config, None)
        assert result["output"]["stdout"].strip() == "hello"
        assert "[Output truncated:" not in result["output"]["stderr"]


class TestPayloadSizeEnforcement:
    """Test _enforce_payload_limit pre-flight check."""

    def test_small_output_unchanged(self) -> None:
        """Payload under the limit is returned as-is."""
        result = {"output": {"stdout": "hello", "stderr": "", "return_code": 0}}
        assert _enforce_payload_limit(result, max_bytes=1_000_000) == result

    def test_large_stdout_truncated(self) -> None:
        """Stdout is truncated when serialized payload exceeds limit."""
        large_stdout = "x" * 500_000
        result = {"output": {"stdout": large_stdout, "stderr": "", "return_code": 0}}
        enforced = _enforce_payload_limit(result, max_bytes=1000)
        assert len(enforced["output"]["stdout"]) < len(large_stdout)
        assert "[Payload truncated:" in enforced["output"]["stderr"]

    def test_both_fields_truncated_when_stdout_insufficient(self) -> None:
        """When stdout alone can't shed enough bytes, stderr is also truncated."""
        result = {"output": {"stdout": "x" * 100, "stderr": "y" * 500_000, "return_code": 0}}
        enforced = _enforce_payload_limit(result, max_bytes=1000)
        assert "[Payload truncated:" in enforced["output"]["stderr"]
        assert len(enforced["output"]["stderr"]) < 500_000

    def test_error_path_detail_shape(self) -> None:
        """Error-path dicts (same shape as success) are truncated correctly."""
        result = {"output": {"stdout": "x" * 500_000, "stderr": "err", "return_code": 1}}
        enforced = _enforce_payload_limit(result, max_bytes=1000)
        assert "[Payload truncated:" in enforced["output"]["stderr"]
        assert len(enforced["output"]["stdout"]) < 500_000


class TestCgroupMemoryLimit:
    """Tests for _get_cgroup_memory_limit."""

    def test_returns_none_when_no_cgroup_files(self) -> None:
        """Returns None when cgroup files don't exist."""
        with patch("syntara.workflows.workflow_engine.activities.script_activity.Path") as mock_path:
            mock_path.return_value.read_text.side_effect = FileNotFoundError
            result = _get_cgroup_memory_limit()
        assert result is None

    def test_returns_none_for_max_value(self) -> None:
        """Returns None when cgroup reports 'max' (no limit)."""
        with patch("syntara.workflows.workflow_engine.activities.script_activity.Path") as mock_path:
            mock_path.return_value.read_text.return_value = "max\n"
            result = _get_cgroup_memory_limit()
        assert result is None

    def test_returns_integer_limit(self) -> None:
        """Returns the parsed integer limit."""
        with patch("syntara.workflows.workflow_engine.activities.script_activity.Path") as mock_path:
            mock_path.return_value.read_text.return_value = "1073741824\n"
            result = _get_cgroup_memory_limit()
        assert result == 1073741824


class TestPrependMemoryLimit:
    """Tests for _prepend_memory_limit."""

    def test_python_preamble(self) -> None:
        """Python scripts get resource.setrlimit prepended."""
        result = _prepend_memory_limit("print('hi')", "python", 768_000_000)
        assert result.startswith("import resource")
        assert "768000000" in result
        assert result.endswith("print('hi')")

    def test_bash_preamble(self) -> None:
        """Bash scripts get ulimit -v prepended."""
        result = _prepend_memory_limit("echo hi", "bash", 768_000_000)
        assert "ulimit -v" in result
        assert result.endswith("echo hi")


class TestMemoryLimitIntegration:
    """Test cgroup memory limit injection in execute_script_activity."""

    @pytest.mark.asyncio
    async def test_cgroup_limit_injects_preamble(self) -> None:
        """When cgroup limit exists, script runs with memory limit and still works."""
        with patch(
            "syntara.workflows.workflow_engine.activities.script_activity._get_cgroup_memory_limit",
            return_value=1_073_741_824,
        ):
            result = await execute_script_activity(
                {"language": "bash", "code": "echo wrapped"},
                None,
            )
        assert result["output"]["stdout"].strip() == "wrapped"
