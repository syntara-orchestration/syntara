"""Unit tests for JSON Schema validation helpers.

Tests cover:
- Definition-time validation (meta-schema, $ref rejection, ReDoS detection)
- Runtime payload validation with $ref resolution blocked
"""

from typing import Any, ClassVar

import jsonschema
import pytest
from referencing.exceptions import Unresolvable

from syntara.workflows.json_schema_validation import (
    _has_dangerous_pattern,
    apply_schema_defaults,
    validate_json_schema_definition,
)

# ============================================================================
# validate_json_schema_definition
# ============================================================================


class TestValidateJsonSchemaDefinition:
    """Test suite for definition-time schema validation."""

    def test_valid_schema_passes(self) -> None:
        """A well-formed Draft-07 schema should pass validation."""
        schema = {
            "type": "object",
            "properties": {"event": {"type": "string"}},
            "required": ["event"],
        }
        # Should not raise
        validate_json_schema_definition(schema)

    def test_valid_schema_with_pattern_passes(self) -> None:
        """A schema with a safe regex pattern should pass."""
        schema = {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "pattern": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
                },
            },
        }
        validate_json_schema_definition(schema)

    def test_empty_object_schema_passes(self) -> None:
        """A minimal schema with just a type should pass."""
        validate_json_schema_definition({"type": "object"})

    def test_invalid_meta_schema_raises(self) -> None:
        """A structurally invalid schema should be rejected."""
        schema = {"type": "not_a_valid_type"}
        with pytest.raises(ValueError, match="Invalid JSON Schema"):
            validate_json_schema_definition(schema)

    def test_ref_at_top_level_rejected(self) -> None:
        """A $ref at the top level should be rejected."""
        schema = {"$ref": "http://internal-service/secret"}
        with pytest.raises(ValueError, match=r"\$ref"):
            validate_json_schema_definition(schema)

    def test_ref_in_properties_rejected(self) -> None:
        """A $ref nested inside properties should be rejected."""
        schema = {
            "type": "object",
            "properties": {
                "data": {"$ref": "http://malicious.example.com/schema"},
            },
        }
        with pytest.raises(ValueError, match=r"\$ref"):
            validate_json_schema_definition(schema)

    def test_ref_in_items_rejected(self) -> None:
        """A $ref inside array items should be rejected."""
        schema = {
            "type": "array",
            "items": {"$ref": "#/definitions/Thing"},
        }
        with pytest.raises(ValueError, match=r"\$ref"):
            validate_json_schema_definition(schema)

    def test_ref_in_allof_rejected(self) -> None:
        """A $ref inside allOf should be rejected."""
        schema = {
            "allOf": [
                {"type": "object"},
                {"$ref": "https://example.com/base.json"},
            ],
        }
        with pytest.raises(ValueError, match=r"\$ref"):
            validate_json_schema_definition(schema)

    def test_local_ref_rejected(self) -> None:
        """Even local JSON Pointer $ref should be rejected."""
        schema = {
            "type": "object",
            "properties": {
                "child": {"$ref": "#/definitions/Child"},
            },
            "definitions": {
                "Child": {"type": "string"},
            },
        }
        with pytest.raises(ValueError, match=r"\$ref"):
            validate_json_schema_definition(schema)

    def test_invalid_regex_pattern_rejected(self) -> None:
        """A pattern with invalid regex syntax should be rejected.

        Draft-07 meta-schema validation catches invalid regex patterns
        via the ``format: regex`` check before our walker runs.
        """
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "pattern": "[invalid"},
            },
        }
        with pytest.raises(ValueError, match="Invalid JSON Schema"):
            validate_json_schema_definition(schema)

    def test_redos_nested_quantifier_rejected(self) -> None:
        """A pattern with nested quantifiers (ReDoS) should be rejected."""
        schema = {
            "type": "object",
            "properties": {
                "data": {"type": "string", "pattern": "(a+)+$"},
            },
        }
        with pytest.raises(ValueError, match="Potentially unsafe regex"):
            validate_json_schema_definition(schema)

    def test_redos_nested_star_rejected(self) -> None:
        """Nested star quantifiers should be rejected."""
        schema = {
            "type": "object",
            "properties": {
                "data": {"type": "string", "pattern": "(x*y*)*z"},
            },
        }
        with pytest.raises(ValueError, match="Potentially unsafe regex"):
            validate_json_schema_definition(schema)

    def test_pattern_in_nested_schema_checked(self) -> None:
        """Dangerous patterns in deeply nested schemas should still be caught."""
        schema = {
            "type": "object",
            "properties": {
                "outer": {
                    "type": "object",
                    "properties": {
                        "inner": {
                            "type": "string",
                            "pattern": "(a+)+",
                        },
                    },
                },
            },
        }
        with pytest.raises(ValueError, match="Potentially unsafe regex"):
            validate_json_schema_definition(schema)

    def test_safe_quantifiers_pass(self) -> None:
        """Non-nested quantifiers should be allowed."""
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": r"^[a-z0-9]+$"},
                "version": {"type": "string", "pattern": r"^\d{1,3}\.\d{1,3}$"},
            },
        }
        validate_json_schema_definition(schema)

    def test_pattern_properties_redos_rejected(self) -> None:
        """A patternProperties key with nested quantifiers should be rejected."""
        schema = {
            "type": "object",
            "patternProperties": {
                "(a+)+$": {"type": "string"},
            },
        }
        with pytest.raises(ValueError, match="Potentially unsafe regex"):
            validate_json_schema_definition(schema)

    def test_pattern_properties_invalid_regex_rejected(self) -> None:
        """A patternProperties key with invalid regex should be rejected.

        Draft-07 meta-schema validation catches invalid regex in
        patternProperties keys via the ``format: regex`` check.
        """
        schema = {
            "type": "object",
            "patternProperties": {
                "[invalid": {"type": "string"},
            },
        }
        with pytest.raises(ValueError, match="Invalid JSON Schema"):
            validate_json_schema_definition(schema)

    def test_pattern_properties_safe_key_passes(self) -> None:
        """A patternProperties key with a safe regex should pass."""
        schema = {
            "type": "object",
            "patternProperties": {
                r"^[a-z]+$": {"type": "string"},
            },
        }
        validate_json_schema_definition(schema)


# ============================================================================
# _has_dangerous_pattern
# ============================================================================


class TestHasDangerousPattern:
    """Test the ReDoS heuristic directly."""

    @pytest.mark.parametrize(
        "pattern",
        [
            "(a+)+",
            "(a+)+$",
            "(x*y*)*z",
            "(a|b+)*c",
            "(a{2,})+",
        ],
    )
    def test_dangerous_patterns_detected(self, pattern: str) -> None:
        """Known ReDoS patterns should be flagged."""
        assert _has_dangerous_pattern(pattern) is True

    @pytest.mark.parametrize(
        "pattern",
        [
            r"^[a-z]+$",
            r"^\d{3}-\d{4}$",
            r"^(foo|bar)$",
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            r"^\w+$",
        ],
    )
    def test_safe_patterns_pass(self, pattern: str) -> None:
        """Safe regex patterns should not be flagged."""
        assert _has_dangerous_pattern(pattern) is False


# ============================================================================
# apply_schema_defaults
# ============================================================================


class TestApplySchemaDefaults:
    """Test suite for default-filling schema validation."""

    SCHEMA: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "version": {"type": "string", "default": "latest"},
            "timeout": {"type": "integer", "default": 30},
            "name": {"type": "string"},
        },
    }

    def test_empty_input_gets_all_defaults(self) -> None:
        data: dict[str, Any] = {}
        apply_schema_defaults(data, self.SCHEMA)
        assert data == {"version": "latest", "timeout": 30}

    def test_partial_input_gets_missing_defaults(self) -> None:
        data = {"version": "1.0"}
        apply_schema_defaults(data, self.SCHEMA)
        assert data == {"version": "1.0", "timeout": 30}

    def test_complete_input_unchanged(self) -> None:
        data = {"version": "1.0", "timeout": 60, "name": "test"}
        apply_schema_defaults(data, self.SCHEMA)
        assert data == {"version": "1.0", "timeout": 60, "name": "test"}

    def test_user_value_not_overridden(self) -> None:
        data = {"version": "1.0"}
        apply_schema_defaults(data, self.SCHEMA)
        assert data["version"] == "1.0"

    def test_schema_without_properties_is_noop(self) -> None:
        data = {"key": "value"}
        apply_schema_defaults(data, {"type": "object"})
        assert data == {"key": "value"}

    def test_no_defaults_in_schema_is_noop(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        data = {"name": "test"}
        apply_schema_defaults(data, schema)
        assert data == {"name": "test"}

    def test_non_object_schema_validates(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            apply_schema_defaults({"key": "value"}, {"type": "array", "items": {"type": "string"}})

    def test_mixed_default_types(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "s": {"type": "string", "default": "hello"},
                "i": {"type": "integer", "default": 42},
                "b": {"type": "boolean", "default": True},
                "a": {"type": "array", "default": [1, 2]},
                "o": {"type": "object", "default": {"nested": True}},
            },
        }
        data: dict[str, Any] = {}
        apply_schema_defaults(data, schema)
        assert data == {"s": "hello", "i": 42, "b": True, "a": [1, 2], "o": {"nested": True}}

    def test_null_default_applied(self) -> None:
        schema = {
            "type": "object",
            "properties": {"value": {"type": ["string", "null"], "default": None}},
        }
        data: dict[str, Any] = {}
        apply_schema_defaults(data, schema)
        assert data == {"value": None}

    def test_mutates_in_place(self) -> None:
        data: dict[str, Any] = {}
        apply_schema_defaults(data, self.SCHEMA)
        assert data == {"version": "latest", "timeout": 30}

    def test_invalid_input_raises_validation_error(self) -> None:
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }
        with pytest.raises(jsonschema.ValidationError):
            apply_schema_defaults({"count": "not_an_int"}, schema)

    def test_ref_resolution_blocked(self) -> None:
        schema = {
            "type": "object",
            "properties": {"data": {"$ref": "http://internal-service/secret"}},
        }
        with pytest.raises(Unresolvable):
            apply_schema_defaults({"data": "test"}, schema)

    def test_required_field_with_default_passes(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "default": "anon"}},
            "required": ["name"],
        }
        data: dict[str, Any] = {}
        apply_schema_defaults(data, schema)
        assert data == {"name": "anon"}

    def test_mutable_defaults_not_aliased(self) -> None:
        """Mutable defaults are deep-copied so mutations don't corrupt the schema."""
        tags_prop: dict[str, Any] = {"type": "array", "default": ["a", "b"]}
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"tags": tags_prop},
        }
        data1: dict[str, Any] = {}
        data2: dict[str, Any] = {}
        apply_schema_defaults(data1, schema)
        apply_schema_defaults(data2, schema)
        data1["tags"].append("c")
        assert data2["tags"] == ["a", "b"]
        assert tags_prop["default"] == ["a", "b"]

    def test_non_dict_instance_does_not_crash(self) -> None:
        """Non-dict instance raises ValidationError, not AttributeError."""
        schema = {"type": "object", "properties": {"x": {"type": "string", "default": "hi"}}}
        with pytest.raises(jsonschema.ValidationError):
            apply_schema_defaults([1, 2, 3], schema)  # type: ignore[arg-type]
