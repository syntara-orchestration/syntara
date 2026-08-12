"""Unit tests for agent orchestrator query parameter models."""

import pytest
from pydantic import ValidationError

from syntara.agent_orchestrator.models.query_params import StreamingQueryParams


class TestStreamingQueryParams:
    """Test cases for StreamingQueryParams validation."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        params = StreamingQueryParams()
        assert params.replay_count == "10"
        assert params.last_event_id is None

    def test_valid_replay_count_special_all(self) -> None:
        """Test replay_count with special value 'all'."""
        params = StreamingQueryParams(replay_count="all")
        assert params.replay_count == "all"

    def test_valid_replay_count_special_zero(self) -> None:
        """Test replay_count with special value '0'."""
        params = StreamingQueryParams(replay_count="0")
        assert params.replay_count == "0"

    def test_valid_replay_count_numeric_string(self) -> None:
        """Test replay_count with valid numeric strings."""
        # Test various valid numeric values
        for value in ["1", "10", "100", "999", "1000", "5000"]:
            params = StreamingQueryParams(replay_count=value)
            assert params.replay_count == value

    def test_invalid_replay_count_negative(self) -> None:
        """Test replay_count rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            StreamingQueryParams(replay_count="-1")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "non-negative" in errors[0]["msg"]

    def test_invalid_replay_count_non_numeric(self) -> None:
        """Test replay_count rejects non-numeric strings."""
        with pytest.raises(ValidationError) as exc_info:
            StreamingQueryParams(replay_count="invalid")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "must be 'all', '0', or a non-negative integer string" in errors[0]["msg"]

    def test_invalid_replay_count_float(self) -> None:
        """Test replay_count rejects float values."""
        with pytest.raises(ValidationError) as exc_info:
            StreamingQueryParams(replay_count="10.5")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "must be 'all', '0', or a non-negative integer string" in errors[0]["msg"]

    def test_valid_last_event_id_none(self) -> None:
        """Test last_event_id with None value."""
        params = StreamingQueryParams(last_event_id=None)
        assert params.last_event_id is None

    def test_valid_last_event_id_special_zero(self) -> None:
        """Test last_event_id with special value '0'."""
        params = StreamingQueryParams(last_event_id="0")
        assert params.last_event_id == "0"

    def test_valid_last_event_id_special_dollar(self) -> None:
        """Test last_event_id with special value '$'."""
        params = StreamingQueryParams(last_event_id="$")
        assert params.last_event_id == "$"

    def test_valid_last_event_id_timestamp_sequence(self) -> None:
        """Test last_event_id with valid timestamp-sequence format."""
        # Test various valid Redis stream IDs
        valid_ids = [
            "1691431234567-0",
            "1691431234567-42",
            "123-456",
            "9999999999999-9999",
        ]
        for event_id in valid_ids:
            params = StreamingQueryParams(last_event_id=event_id)
            assert params.last_event_id == event_id

    def test_invalid_last_event_id_no_dash(self) -> None:
        """Test last_event_id rejects format without dash."""
        with pytest.raises(ValidationError) as exc_info:
            StreamingQueryParams(last_event_id="1691431234567")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "must be in format 'timestamp-sequence'" in errors[0]["msg"]

    def test_invalid_last_event_id_multiple_dashes(self) -> None:
        """Test last_event_id rejects format with multiple dashes."""
        with pytest.raises(ValidationError) as exc_info:
            StreamingQueryParams(last_event_id="123-456-789")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "must be in format 'timestamp-sequence'" in errors[0]["msg"]

    def test_invalid_last_event_id_non_numeric_parts(self) -> None:
        """Test last_event_id rejects non-numeric parts."""
        invalid_ids = [
            "abc-123",
            "123-def",
            "abc-def",
            "123-",
            "-456",
        ]
        for event_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                StreamingQueryParams(last_event_id=event_id)

            errors = exc_info.value.errors()
            assert len(errors) == 1
            assert "must be in format 'timestamp-sequence'" in errors[0]["msg"]

    def test_valid_combined_parameters(self) -> None:
        """Test valid combination of both parameters."""
        params = StreamingQueryParams(replay_count="50", last_event_id="1691431234567-42")
        assert params.replay_count == "50"
        assert params.last_event_id == "1691431234567-42"

    def test_validation_from_dict(self) -> None:
        """Test validation works when initialized from dict (like query params)."""
        # Simulate FastAPI query_params dict
        query_dict = {"replay_count": "25", "last_event_id": "1234567890-5"}
        params = StreamingQueryParams(**query_dict)
        assert params.replay_count == "25"
        assert params.last_event_id == "1234567890-5"

    def test_validation_with_extra_fields_ignored(self) -> None:
        """Test that extra fields are ignored (SQLModel default behavior)."""
        # SQLModel by default ignores extra fields
        params = StreamingQueryParams(replay_count="10", last_event_id="123-456", extra_field="should_be_ignored")
        assert params.replay_count == "10"
        assert params.last_event_id == "123-456"
        # extra_field should not be set
        assert not hasattr(params, "extra_field")
