"""Unit tests for audit data truncation utilities."""

# mypy: disable-error-code="attr-defined"

import json

from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.truncation import DEFAULT_MAX_PAYLOAD_BYTES, enforce_payload_limit


class TestEnforcePayloadLimit:
    """Tests for enforce_payload_limit truncation behavior."""

    def test_under_limit_no_truncation(self) -> None:
        """Data under max_bytes is left unchanged."""
        data = AuditContextData(data_type="test", function_args={"a": 1, "b": 2})
        original_data = data.model_copy()
        result = enforce_payload_limit(data, max_bytes=DEFAULT_MAX_PAYLOAD_BYTES)
        assert result.function_args == original_data.function_args

    def test_string_leaf_in_dict_truncated_preserves_structure(self) -> None:
        """A large string inside a dict is truncated but the dict structure is preserved."""
        limit = DEFAULT_MAX_PAYLOAD_BYTES // 10
        large_value = "x" * (DEFAULT_MAX_PAYLOAD_BYTES * 2)
        data = AuditContextData(data_type="test", function_args={"payload": large_value})
        result = enforce_payload_limit(data, max_bytes=limit)

        # Dict structure should be preserved
        assert isinstance(result.function_args, dict)
        assert "payload" in result.function_args
        # The string value inside should be truncated
        assert "...<truncated>" in result.function_args["payload"]
        assert len(result.function_args["payload"]) < len(large_value)

    def test_string_leaf_in_result_dict_truncated(self) -> None:
        """A large string inside function_result dict is truncated, preserving structure."""
        limit = DEFAULT_MAX_PAYLOAD_BYTES // 10
        large_value = "y" * (DEFAULT_MAX_PAYLOAD_BYTES * 2)
        data = AuditContextData(data_type="test", function_result={"output": large_value})
        result = enforce_payload_limit(data, max_bytes=limit)

        assert isinstance(result.function_result, dict)
        assert "...<truncated>" in result.function_result["output"]

    def test_multiple_dicts_both_truncated(self) -> None:
        """Large strings in both function_args and function_result are truncated."""
        limit = DEFAULT_MAX_PAYLOAD_BYTES // 10
        data = AuditContextData(
            data_type="test",
            function_args={"payload": "a" * (DEFAULT_MAX_PAYLOAD_BYTES * 2)},
            function_result={"output": "b" * (DEFAULT_MAX_PAYLOAD_BYTES * 2)},
        )
        result = enforce_payload_limit(data, max_bytes=limit)

        # Both dicts preserved with truncated string leaves
        assert isinstance(result.function_args, dict)
        assert "...<truncated>" in result.function_args["payload"]
        assert isinstance(result.function_result, dict)
        assert "...<truncated>" in result.function_result["output"]

    def test_top_level_string_field_truncated(self) -> None:
        """A top-level string field (not inside a dict) is truncated directly."""
        limit = DEFAULT_MAX_PAYLOAD_BYTES // 10
        data = AuditContextData(data_type="test", error_message="x" * (DEFAULT_MAX_PAYLOAD_BYTES * 5))
        result = enforce_payload_limit(data, max_bytes=limit)
        assert isinstance(result.error_message, str)
        assert "...<truncated>" in result.error_message

    def test_nested_dict_string_leaves_truncated(self) -> None:
        """Deeply nested string values are found and truncated."""
        limit = 200
        data = AuditContextData(
            data_type="test",
            function_args={
                "query": {"sql": "SELECT " + "x" * 500, "params": {"id": 42}},
                "context": "short",
            },
        )
        result = enforce_payload_limit(data, max_bytes=limit)

        # Structure preserved at all levels
        assert isinstance(result.function_args, dict)
        assert isinstance(result.function_args["query"], dict)
        assert isinstance(result.function_args["query"]["params"], dict)
        # The large nested string is truncated
        assert "...<truncated>" in result.function_args["query"]["sql"]
        # Non-string values untouched
        assert result.function_args["query"]["params"]["id"] == 42

    def test_list_string_leaves_truncated(self) -> None:
        """Strings inside lists are found and truncated."""
        limit = 200
        data = AuditContextData(
            data_type="test",
            function_args={"items": ["short", "a" * 500, "also_short"]},
        )
        result = enforce_payload_limit(data, max_bytes=limit)

        assert isinstance(result.function_args, dict)
        assert isinstance(result.function_args["items"], list)
        assert len(result.function_args["items"]) == 3
        # The large string in the list should be truncated
        assert "...<truncated>" in result.function_args["items"][1]
        # Short strings preserved if budget allows
        assert result.function_args["items"][0] == "short"

    def test_non_string_values_never_modified(self) -> None:
        """Ints, bools, None, and other non-string types are never touched."""
        limit = 100
        data = AuditContextData(
            data_type="test",
            function_args={
                "count": 999999,
                "flag": True,
                "empty": None,
                "big_text": "x" * 500,
            },
        )
        result = enforce_payload_limit(data, max_bytes=limit)

        assert isinstance(result.function_args, dict)
        assert result.function_args["count"] == 999999
        assert result.function_args["flag"] is True
        assert result.function_args["empty"] is None
        # Only the string got truncated
        assert "...<truncated>" in result.function_args["big_text"]

    def test_empty_data_no_crash(self) -> None:
        """Empty data structures don't cause crashes."""
        data = AuditContextData(data_type="test")
        result = enforce_payload_limit(data, max_bytes=10)
        assert result is not None

    def test_value_already_at_suffix_length(self) -> None:
        """Values already at or below suffix length can't be truncated further."""
        short_value = "ab"
        data = AuditContextData(data_type="test", function_args={"short": short_value})
        result = enforce_payload_limit(data, max_bytes=200)
        assert result.function_args == {"short": short_value}

    def test_multiple_string_leaves_truncated_iteratively(self) -> None:
        """Multiple large string leaves are truncated across iterations."""
        limit = 200
        data = AuditContextData(
            data_type="test",
            function_args={"large1": "a" * 300, "large2": "b" * 300, "small": "c"},
        )
        result = enforce_payload_limit(data, max_bytes=limit)
        total_size = len(json.dumps(result.model_dump(), default=str).encode())
        assert total_size <= limit + 50  # allow margin for overhead

        # Dict structure preserved, both large values truncated
        assert isinstance(result.function_args, dict)
        assert "...<truncated>" in result.function_args["large1"]
        assert "...<truncated>" in result.function_args["large2"]

    def test_zero_max_bytes_edge_case(self) -> None:
        """Extremely small max_bytes doesn't cause infinite loops."""
        data = AuditContextData(data_type="test", function_args={"any": "data"})
        result = enforce_payload_limit(data, max_bytes=0)
        assert result is not None

    def test_max_bytes_smaller_than_overhead_terminates(self) -> None:
        """When max_bytes is smaller than structural overhead, truncation terminates."""
        data = AuditContextData(
            data_type="test",
            function_args={"payload": "a" * (DEFAULT_MAX_PAYLOAD_BYTES // 10)},
            function_result={"output": "b" * (DEFAULT_MAX_PAYLOAD_BYTES // 10)},
            error_message="c" * (DEFAULT_MAX_PAYLOAD_BYTES // 10),
        )
        result = enforce_payload_limit(data, max_bytes=10)
        # Should terminate without hanging — string leaves truncated
        assert isinstance(result.function_args, dict)
        assert "...<truncated>" in result.function_args["payload"]
        assert isinstance(result.function_result, dict)
        assert "...<truncated>" in result.function_result["output"]
        assert isinstance(result.error_message, str)
        assert "...<truncated>" in result.error_message

    def test_audit_context_data_extra_fields_truncated(self) -> None:
        """AuditContextData with extra='allow' has oversized extra fields truncated."""
        large_value = "x" * 20_000
        data = AuditContextData(data_type="test", large_field=large_value)
        result = enforce_payload_limit(data, max_bytes=DEFAULT_MAX_PAYLOAD_BYTES)

        assert isinstance(result, AuditContextData)
        result_dict = result.model_dump()
        assert "...<truncated>" in result_dict["large_field"]

    def test_no_string_leaves_returns_original(self) -> None:
        """When there are no string leaves to truncate, the original is returned."""
        data = AuditContextData(data_type="test", function_args={"count": 1, "flag": True})
        result = enforce_payload_limit(data, max_bytes=5)
        # No string leaves to truncate, so even though over budget, original returned
        assert result.function_args == {"count": 1, "flag": True}

    def test_no_progress_on_largest_leaf_continues_to_others(self) -> None:
        """When the largest leaf can't be reduced, the loop skips it and truncates others."""
        # Create data where one leaf is already very short (can't be reduced below the
        # truncation suffix) but another leaf is large and can still be truncated.
        tiny_value = "x"  # Shorter than the truncation suffix — will trigger the no-progress guard
        large_value = "y" * 20_000  # Can be truncated
        data = AuditContextData(
            data_type="test",
            function_args={"tiny": tiny_value, "large": large_value},
        )
        # Set a limit that forces truncation but is large enough that
        # truncating only "large" should bring us under budget
        limit = 300
        result = enforce_payload_limit(data, max_bytes=limit)

        assert isinstance(result.function_args, dict)
        # The large value should have been truncated
        assert "...<truncated>" in result.function_args["large"]
        assert len(result.function_args["large"]) < len(large_value)
        # The tiny value should remain unchanged (it was skipped, not corrupted)
        assert result.function_args["tiny"] == tiny_value

    def test_returns_new_instance(self) -> None:
        """Truncation returns a new model instance, not the original."""
        large_value = "x" * 20_000
        data = AuditContextData(data_type="test", function_args={"payload": large_value})
        result = enforce_payload_limit(data, max_bytes=DEFAULT_MAX_PAYLOAD_BYTES)

        # Should be a different instance
        assert result is not data
        # Original should be unmodified
        assert data.function_args == {"payload": large_value}
