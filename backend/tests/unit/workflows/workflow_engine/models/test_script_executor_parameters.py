"""Tests for ScriptExecutorParameters environment coercion."""

from syntara.workflows.workflow_engine.models.workflow_definition import ScriptExecutorParameters, ScriptLanguage


class TestScriptExecutorParametersEnvironmentCoercion:
    """Test that environment values are coerced to strings."""

    def test_string_values_unchanged(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
            environment={"VAR": "hello"},
        )
        assert params.environment == {"VAR": "hello"}

    def test_integer_values_coerced_to_string(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
            environment={"RETURN_CODE": 0, "COUNT": 42},  # type: ignore[dict-item]
        )
        assert params.environment == {"RETURN_CODE": "0", "COUNT": "42"}

    def test_float_values_coerced_to_string(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
            environment={"RATIO": 3.14},  # type: ignore[dict-item]
        )
        assert params.environment == {"RATIO": "3.14"}

    def test_bool_values_coerced_to_json_string(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
            environment={"FLAG": True, "OFF": False},  # type: ignore[dict-item]
        )
        assert params.environment == {"FLAG": "true", "OFF": "false"}

    def test_dict_values_coerced_to_json_string(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
            environment={"CONFIG": {"host": "localhost"}},  # type: ignore[dict-item]
        )
        assert params.environment == {"CONFIG": '{"host": "localhost"}'}

    def test_list_values_coerced_to_json_string(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
            environment={"ITEMS": ["a", "b"]},  # type: ignore[dict-item]
        )
        assert params.environment == {"ITEMS": '["a", "b"]'}

    def test_empty_environment(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
        )
        assert params.environment == {}

    def test_mixed_types_all_coerced(self) -> None:
        params = ScriptExecutorParameters(
            language=ScriptLanguage.PYTHON,
            code="pass",
            environment={"A": "str", "B": 1, "C": True, "D": 2.5},  # type: ignore[dict-item]
        )
        assert params.environment == {"A": "str", "B": "1", "C": "true", "D": "2.5"}
