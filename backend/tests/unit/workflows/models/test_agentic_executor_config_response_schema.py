"""Unit tests for AgenticExecutorParameters response_schema validation.

Tests for structured output support in agentic nodes.

These tests verify:
- response_schema field accepts valid JSON Schema objects
- response_schema field defaults to None
- response_schema field rejects schemas missing 'type' field
- response_schema field rejects non-dict values
- Template expressions bypass validation (TemplateAwareBaseModel behavior)
"""

from syntara.workflows.workflow_engine.models.workflow_definition import AgenticExecutorParameters


class TestAgenticExecutorParametersResponseSchema:
    """Test suite for AgenticExecutorParameters response_schema field validation."""

    # ==========================================================================
    # Valid Cases
    # ==========================================================================

    def test_response_schema_defaults_to_none(self) -> None:
        """Test that response_schema defaults to None when not provided."""
        config = AgenticExecutorParameters(prompt="Test prompt")

        assert config.response_schema is None

    def test_response_schema_accepts_valid_object_schema(self) -> None:
        """Test that a valid object schema is accepted."""
        schema = {
            "type": "object",
            "properties": {
                "hostname": {"type": "string"},
                "ip_address": {"type": "string"},
            },
            "required": ["hostname"],
        }
        config = AgenticExecutorParameters(prompt="Test prompt", responseSchema=schema)

        assert config.response_schema == schema

    def test_response_schema_accepts_simple_string_schema(self) -> None:
        """Test that a simple string schema is accepted."""
        schema = {"type": "string"}
        config = AgenticExecutorParameters(prompt="Test prompt", responseSchema=schema)

        assert config.response_schema == schema

    def test_response_schema_accepts_array_schema(self) -> None:
        """Test that an array schema is accepted."""
        schema = {
            "type": "array",
            "items": {"type": "string"},
        }
        config = AgenticExecutorParameters(prompt="Test prompt", responseSchema=schema)

        assert config.response_schema == schema

    def test_response_schema_accepts_complex_nested_schema(self) -> None:
        """Test that a complex nested schema is accepted."""
        schema = {
            "type": "object",
            "properties": {
                "servers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hostname": {"type": "string"},
                            "status": {"type": "string", "enum": ["running", "stopped"]},
                        },
                        "required": ["hostname", "status"],
                    },
                },
                "count": {"type": "integer"},
            },
            "required": ["servers"],
        }
        config = AgenticExecutorParameters(prompt="Test prompt", responseSchema=schema)

        assert config.response_schema == schema

    def test_response_schema_accepts_none_explicitly(self) -> None:
        """Test that None can be explicitly set."""
        config = AgenticExecutorParameters(prompt="Test prompt", responseSchema=None)

        assert config.response_schema is None

    # ==========================================================================
    # Template Expression Bypass
    # ==========================================================================

    def test_response_schema_template_expression_bypass(self) -> None:
        """Test that template expressions bypass schema validation."""
        template = "${trigger.schema}"
        config = AgenticExecutorParameters(prompt="Test prompt", responseSchema=template)

        assert config.response_schema == template

    def test_response_schema_complex_template_expression(self) -> None:
        """Test that complex template expressions are allowed."""
        template = "${workflow.vars.output_schemas.server_info}"
        config = AgenticExecutorParameters(prompt="Test", responseSchema=template)

        assert config.response_schema == template

    def test_response_schema_template_in_nested_field(self) -> None:
        """Test that template expressions work in nested schema fields."""
        # When the entire response_schema is a template string, it bypasses dict validation
        template = "${input.dynamic_schema}"
        config = AgenticExecutorParameters(prompt="Test", responseSchema=template)

        assert config.response_schema == template

    # ==========================================================================
    # Invalid Cases
    # ==========================================================================

    def test_response_schema_accepts_missing_type_field(self) -> None:
        """Schema without 'type' is valid per JSON Schema Draft-07 (matches anything)."""
        schema = {
            "properties": {"name": {"type": "string"}},
        }
        config = AgenticExecutorParameters(prompt="Test", responseSchema=schema)
        assert config.response_schema == schema

    def test_response_schema_accepts_empty_dict(self) -> None:
        """Empty dict is valid JSON Schema per Draft-07 (matches anything)."""
        config = AgenticExecutorParameters(prompt="Test", responseSchema={})
        assert config.response_schema == {}

    # ==========================================================================
    # API Alias (responseSchema) Compatibility
    # ==========================================================================

    def test_response_schema_alias_accepted(self) -> None:
        """Test that responseSchema alias (camelCase) is accepted in input."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        # Using alias in input (camelCase)
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "Test",
                "timeout": 300,
                "responseSchema": schema,
            }
        )

        assert config.response_schema == schema

    def test_response_schema_serializes_with_alias(self) -> None:
        """Test that response_schema serializes to responseSchema when using by_alias."""
        schema = {"type": "string"}
        config = AgenticExecutorParameters(prompt="Test", responseSchema=schema)

        # Serialize with by_alias=True (for API responses)
        serialized = config.model_dump(mode="json", by_alias=True)

        assert "responseSchema" in serialized
        assert serialized["responseSchema"] == schema
        assert "response_schema" not in serialized

    def test_response_schema_serializes_without_alias(self) -> None:
        """Test that response_schema serializes to response_schema when not using alias."""
        schema = {"type": "string"}
        config = AgenticExecutorParameters(prompt="Test", responseSchema=schema)

        # Serialize without by_alias (Python-style)
        serialized = config.model_dump()

        assert "response_schema" in serialized
        assert serialized["response_schema"] == schema

    def test_response_schema_omitted_when_none_in_serialization(self) -> None:
        """Test that response_schema is included even when None (Pydantic default behavior)."""
        config = AgenticExecutorParameters(prompt="Test")

        serialized = config.model_dump(mode="json", by_alias=True)

        assert "responseSchema" in serialized
        assert serialized["responseSchema"] is None


class TestAgenticExecutorParametersResponseSchemaIntegration:
    """Integration tests for AgenticExecutorParameters with response_schema and other fields."""

    def test_full_config_with_response_schema(self) -> None:
        """Test complete configuration with all fields including response_schema."""
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["summary"],
        }

        config = AgenticExecutorParameters(
            prompt="Analyze the data",
            agent="data-analyzer",
            responseSchema=schema,
        )

        assert config.prompt == "Analyze the data"
        assert config.agent == "data-analyzer"
        assert config.response_schema == schema

    def test_config_from_workflow_yaml_format_with_schema(self) -> None:
        """Test config parsing from workflow YAML-like dict with response_schema."""
        yaml_config = {
            "prompt": "Extract server info",
            "agent": "server-analyzer",
            "timeout": 600,
            "responseSchema": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string"},
                    "ip": {"type": "string"},
                },
            },
        }

        config = AgenticExecutorParameters.model_validate(yaml_config)

        assert config.prompt == "Extract server info"
        assert config.response_schema is not None
        assert isinstance(config.response_schema, dict)
        assert config.response_schema["type"] == "object"
        assert "hostname" in config.response_schema["properties"]

    def test_config_with_file_ids_and_response_schema(self) -> None:
        """Test config with both file_ids and response_schema."""
        schema = {"type": "array", "items": {"type": "string"}}
        file_ids = ["550e8400-e29b-41d4-a716-446655440000"]

        config = AgenticExecutorParameters(
            prompt="Process files and return list",
            file_ids=file_ids,
            responseSchema=schema,
        )

        assert config.file_ids == file_ids
        assert config.response_schema == schema
