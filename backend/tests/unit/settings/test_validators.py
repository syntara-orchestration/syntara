"""Unit tests for settings validation logic.

Tests cover:
- None values bypass all validation
- Type checking for STRING, INTEGER, FLOAT, BOOLEAN, JSON
- Bool/int ambiguity (Python bool is subclass of int)
- Min/max constraint enforcement
- allowed_values constraint enforcement
- pattern (regex) constraint enforcement
- No schema skips constraint checks
"""

from __future__ import annotations

import pytest

from syntara.settings.exceptions import SettingValidationError
from syntara.settings.models.runtime_setting import SettingValueType
from syntara.settings.validators import check_schema_compatibility, validate_setting_value

# ---------------------------------------------------------------------------
# None bypass
# ---------------------------------------------------------------------------


def test_validate_none_bypasses_all_checks() -> None:
    """value=None must never raise, regardless of type or schema."""
    validate_setting_value(
        key="test.key",
        value=None,
        value_type=SettingValueType.INTEGER,
        validation_schema={"min": 0, "max": 100},
    )


# ---------------------------------------------------------------------------
# Type checking — STRING
# ---------------------------------------------------------------------------


def test_validate_string_type_accepts_string() -> None:
    """STRING type accepts str values."""
    validate_setting_value(
        key="test.key",
        value="hello",
        value_type=SettingValueType.STRING,
        validation_schema=None,
    )


def test_validate_string_type_rejects_int() -> None:
    """STRING type rejects int values."""
    with pytest.raises(SettingValidationError, match="expects type STRING"):
        validate_setting_value(
            key="test.key",
            value=42,
            value_type=SettingValueType.STRING,
            validation_schema=None,
        )


# ---------------------------------------------------------------------------
# Type checking — INTEGER
# ---------------------------------------------------------------------------


def test_validate_integer_type_accepts_int() -> None:
    """INTEGER type accepts int values."""
    validate_setting_value(
        key="test.key",
        value=42,
        value_type=SettingValueType.INTEGER,
        validation_schema=None,
    )


def test_validate_integer_type_rejects_bool() -> None:
    """INTEGER type rejects bool values (bool is subclass of int in Python)."""
    with pytest.raises(SettingValidationError, match="expects type INTEGER"):
        validate_setting_value(
            key="test.key",
            value=True,
            value_type=SettingValueType.INTEGER,
            validation_schema=None,
        )


def test_validate_integer_type_rejects_float() -> None:
    """INTEGER type rejects float values."""
    with pytest.raises(SettingValidationError, match="expects type INTEGER"):
        validate_setting_value(
            key="test.key",
            value=3.14,
            value_type=SettingValueType.INTEGER,
            validation_schema=None,
        )


# ---------------------------------------------------------------------------
# Type checking — FLOAT
# ---------------------------------------------------------------------------


def test_validate_float_type_accepts_float() -> None:
    """FLOAT type accepts float values."""
    validate_setting_value(
        key="test.key",
        value=0.7,
        value_type=SettingValueType.FLOAT,
        validation_schema=None,
    )


def test_validate_float_type_accepts_int_as_float() -> None:
    """FLOAT type accepts int values (int is valid as float)."""
    validate_setting_value(
        key="test.key",
        value=1,
        value_type=SettingValueType.FLOAT,
        validation_schema=None,
    )


def test_validate_float_type_rejects_bool() -> None:
    """FLOAT type rejects bool values."""
    with pytest.raises(SettingValidationError, match="expects type FLOAT"):
        validate_setting_value(
            key="test.key",
            value=True,
            value_type=SettingValueType.FLOAT,
            validation_schema=None,
        )


def test_validate_float_type_rejects_string() -> None:
    """FLOAT type rejects string values."""
    with pytest.raises(SettingValidationError, match="expects type FLOAT"):
        validate_setting_value(
            key="test.key",
            value="0.7",
            value_type=SettingValueType.FLOAT,
            validation_schema=None,
        )


# ---------------------------------------------------------------------------
# Type checking — BOOLEAN
# ---------------------------------------------------------------------------


def test_validate_boolean_type_accepts_bool() -> None:
    """BOOLEAN type accepts bool values."""
    validate_setting_value(
        key="test.key",
        value=True,
        value_type=SettingValueType.BOOLEAN,
        validation_schema=None,
    )


def test_validate_boolean_type_rejects_int() -> None:
    """BOOLEAN type rejects int values."""
    with pytest.raises(SettingValidationError, match="expects type BOOLEAN"):
        validate_setting_value(
            key="test.key",
            value=1,
            value_type=SettingValueType.BOOLEAN,
            validation_schema=None,
        )


# ---------------------------------------------------------------------------
# Type checking — JSON
# ---------------------------------------------------------------------------


def test_validate_json_type_accepts_list() -> None:
    """JSON type accepts list values."""
    validate_setting_value(
        key="test.key",
        value=["a", "b"],
        value_type=SettingValueType.JSON,
        validation_schema=None,
    )


def test_validate_json_type_accepts_dict() -> None:
    """JSON type accepts dict values."""
    validate_setting_value(
        key="test.key",
        value={"nested": True},
        value_type=SettingValueType.JSON,
        validation_schema=None,
    )


def test_validate_json_type_accepts_string() -> None:
    """JSON type accepts any Python type, including str."""
    validate_setting_value(
        key="test.key",
        value="plain string",
        value_type=SettingValueType.JSON,
        validation_schema=None,
    )


def test_validate_json_type_accepts_int() -> None:
    """JSON type accepts any Python type, including int."""
    validate_setting_value(
        key="test.key",
        value=42,
        value_type=SettingValueType.JSON,
        validation_schema=None,
    )


# ---------------------------------------------------------------------------
# Constraint checking — min/max
# ---------------------------------------------------------------------------


def test_validate_min_accepts_at_boundary() -> None:
    """Value equal to min passes validation."""
    validate_setting_value(
        key="test.key",
        value=0.0,
        value_type=SettingValueType.FLOAT,
        validation_schema={"min": 0.0},
    )


def test_validate_min_rejects_below() -> None:
    """Value below min raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match=r"must be >= 0\.0"):
        validate_setting_value(
            key="test.key",
            value=-0.1,
            value_type=SettingValueType.FLOAT,
            validation_schema={"min": 0.0},
        )


def test_validate_max_accepts_at_boundary() -> None:
    """Value equal to max passes validation."""
    validate_setting_value(
        key="test.key",
        value=1.0,
        value_type=SettingValueType.FLOAT,
        validation_schema={"max": 1.0},
    )


def test_validate_max_rejects_above() -> None:
    """Value above max raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match=r"must be <= 1\.0"):
        validate_setting_value(
            key="test.key",
            value=1.1,
            value_type=SettingValueType.FLOAT,
            validation_schema={"max": 1.0},
        )


def test_validate_min_max_range_accepts_within() -> None:
    """Value within a combined min/max range passes validation."""
    validate_setting_value(
        key="test.key",
        value=0.5,
        value_type=SettingValueType.FLOAT,
        validation_schema={"min": 0.0, "max": 1.0},
    )


def test_validate_min_max_range_rejects_below() -> None:
    """Value below a combined min/max range raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match=r"must be >= 0\.0"):
        validate_setting_value(
            key="test.key",
            value=-1.0,
            value_type=SettingValueType.FLOAT,
            validation_schema={"min": 0.0, "max": 1.0},
        )


def test_validate_min_max_range_rejects_above() -> None:
    """Value above a combined min/max range raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match=r"must be <= 1\.0"):
        validate_setting_value(
            key="test.key",
            value=2.0,
            value_type=SettingValueType.FLOAT,
            validation_schema={"min": 0.0, "max": 1.0},
        )


# ---------------------------------------------------------------------------
# Constraint checking — allowed_values
# ---------------------------------------------------------------------------


def test_validate_allowed_values_accepts_valid() -> None:
    """Value in allowed_values list passes validation."""
    validate_setting_value(
        key="test.key",
        value="INFO",
        value_type=SettingValueType.STRING,
        validation_schema={"allowed_values": ["DEBUG", "INFO", "WARNING"]},
    )


def test_validate_allowed_values_rejects_invalid() -> None:
    """Value not in allowed_values list raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match="must be one of"):
        validate_setting_value(
            key="test.key",
            value="TRACE",
            value_type=SettingValueType.STRING,
            validation_schema={"allowed_values": ["DEBUG", "INFO", "WARNING"]},
        )


# ---------------------------------------------------------------------------
# Constraint checking — pattern
# ---------------------------------------------------------------------------


def test_validate_pattern_accepts_matching() -> None:
    """Value matching the regex pattern passes validation."""
    validate_setting_value(
        key="test.key",
        value="ai.model_name",
        value_type=SettingValueType.STRING,
        validation_schema={"pattern": r"^[a-z][a-z0-9_.]+$"},
    )


def test_validate_pattern_rejects_non_matching() -> None:
    """Value not matching the regex pattern raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match="must match pattern"):
        validate_setting_value(
            key="test.key",
            value="INVALID KEY!",
            value_type=SettingValueType.STRING,
            validation_schema={"pattern": r"^[a-z][a-z0-9_.]+$"},
        )


# ---------------------------------------------------------------------------
# No schema
# ---------------------------------------------------------------------------


def test_validate_no_schema_skips_constraints() -> None:
    """When validation_schema is None, only type checking is performed."""
    validate_setting_value(
        key="test.key",
        value=999999,
        value_type=SettingValueType.INTEGER,
        validation_schema=None,
    )


# ---------------------------------------------------------------------------
# Schema-type compatibility
# ---------------------------------------------------------------------------


def test_check_schema_compatibility_rejects_min_on_string() -> None:
    """Min constraint on a STRING type raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match="min/max constraints are only valid"):
        check_schema_compatibility(
            key="test.key",
            value_type=SettingValueType.STRING,
            schema={"min": 0},
        )


def test_check_schema_compatibility_rejects_max_on_boolean() -> None:
    """Max constraint on a BOOLEAN type raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match="min/max constraints are only valid"):
        check_schema_compatibility(
            key="test.key",
            value_type=SettingValueType.BOOLEAN,
            schema={"max": 10},
        )


def test_check_schema_compatibility_rejects_pattern_on_integer() -> None:
    """Pattern constraint on an INTEGER type raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match="pattern constraint is only valid"):
        check_schema_compatibility(
            key="test.key",
            value_type=SettingValueType.INTEGER,
            schema={"pattern": r"^\d+$"},
        )


def test_check_schema_compatibility_rejects_allowed_values_on_integer() -> None:
    """allowed_values constraint on an INTEGER type raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match="allowed_values constraint is only valid"):
        check_schema_compatibility(
            key="test.key",
            value_type=SettingValueType.INTEGER,
            schema={"allowed_values": [1, 2, 3]},
        )


def test_check_schema_compatibility_rejects_min_greater_than_max() -> None:
    """Min > max raises SettingValidationError."""
    with pytest.raises(SettingValidationError, match=r"min \(10\) cannot be greater than max \(5\)"):
        check_schema_compatibility(
            key="test.key",
            value_type=SettingValueType.INTEGER,
            schema={"min": 10, "max": 5},
        )


def test_check_schema_compatibility_accepts_min_equal_to_max() -> None:
    """Min == max is a valid (single-value) constraint."""
    check_schema_compatibility(
        key="test.key",
        value_type=SettingValueType.INTEGER,
        schema={"min": 5, "max": 5},
    )
