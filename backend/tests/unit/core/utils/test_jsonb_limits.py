"""Tests for JSONB field size validation helpers."""

import pytest

from syntara.core.constants import FieldLimits, JsonbLimits
from syntara.core.exceptions import SafeValueError
from syntara.core.jsonb_limits import (
    serialized_json_size,
    validate_jsonb_size,
    validate_labels_dict,
    validate_workflow_definition_json,
)


class TestSerializedJsonSize:
    """Tests for serialized_json_size."""

    def test_empty_dict(self) -> None:
        assert serialized_json_size({}) == 2

    def test_string_value(self) -> None:
        assert serialized_json_size("abc") == 5


class TestValidateJsonbSize:
    """Tests for validate_jsonb_size."""

    def test_accepts_small_payload(self) -> None:
        assert validate_jsonb_size({"a": 1}, field_name="input_data") == {"a": 1}

    def test_rejects_large_payload(self) -> None:
        huge = {"key": "x" * JsonbLimits.MAX_FIELD_BYTES}
        with pytest.raises(SafeValueError, match="input_data exceeds maximum"):
            validate_jsonb_size(huge, field_name="input_data")


class TestValidateLabelsDict:
    """Tests for validate_labels_dict."""

    def test_accepts_valid_labels(self) -> None:
        labels = {"env": "prod", "team": "platform"}
        assert validate_labels_dict(labels) == labels

    def test_rejects_too_many_labels(self) -> None:
        labels = {f"k{i}": "v" for i in range(FieldLimits.MAX_LABELS_COUNT + 1)}
        with pytest.raises(SafeValueError, match="maximum is"):
            validate_labels_dict(labels)

    def test_rejects_long_key(self) -> None:
        key = "k" * (FieldLimits.MAX_LABEL_KEY_LENGTH + 1)
        with pytest.raises(SafeValueError, match="key exceeds maximum length"):
            validate_labels_dict({key: "v"})

    def test_rejects_long_value(self) -> None:
        value = "v" * (FieldLimits.MAX_LABEL_VALUE_LENGTH + 1)
        with pytest.raises(SafeValueError, match="value for key"):
            validate_labels_dict({"env": value})

    def test_rejects_total_serialized_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(FieldLimits, "MAX_LABELS_BYTES", 20)
        with pytest.raises(SafeValueError, match="labels exceeds maximum serialized size"):
            validate_labels_dict({"environment": "production", "region": "us-east-1"})


class TestValidateWorkflowDefinitionJson:
    """Tests for validate_workflow_definition_json."""

    def test_accepts_small_definition(self) -> None:
        definition = {"nodes": [], "edges": []}
        assert validate_workflow_definition_json(definition) == definition

    def test_rejects_oversized_definition(self) -> None:
        definition = {"blob": "x" * JsonbLimits.MAX_WORKFLOW_DEFINITION_BYTES}
        with pytest.raises(SafeValueError, match="workflow_definition exceeds maximum"):
            validate_workflow_definition_json(definition)

    def test_skips_non_dict_values(self) -> None:
        assert validate_workflow_definition_json(None) is None
