"""Unit tests for AuditEvent model."""

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from syntara.audit.models.audit_event import AuditEvent, EventCategory
from syntara.audit.models.structured_data import AuditContextData


class TestAuditEventResourceUrnValidation:
    """Tests for resource_urn RFC 8141 validation."""

    @pytest.mark.parametrize(
        ("input_urn", "expected_urn", "expected_log_fragment"),
        [
            # Valid URNs - should be accepted as-is
            pytest.param(
                "urn:syntara:workflow:uuid:123e4567-e89b-12d3-a456-426614174000",
                "urn:syntara:workflow:uuid:123e4567-e89b-12d3-a456-426614174000",
                None,
                id="valid_urn_syntara_workflow",
            ),
            pytest.param("urn:isbn:0451450523", "urn:isbn:0451450523", None, id="valid_urn_isbn"),
            pytest.param("urn:ietf:rfc:2648", "urn:ietf:rfc:2648", None, id="valid_urn_ietf"),
            pytest.param(
                "urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66",
                "urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66",
                None,
                id="valid_urn_uuid",
            ),
            pytest.param(
                "urn:syntara:resource:12345",
                "urn:syntara:resource:12345",
                None,
                id="valid_urn_syntara_resource",
            ),
            pytest.param(
                "urn:example:animal:ferret:nose",
                "urn:example:animal:ferret:nose",
                None,
                id="valid_urn_example_animal",
            ),
            pytest.param(
                "URN:EXAMPLE:a123,456",
                "URN:EXAMPLE:a123,456",
                None,
                id="valid_urn_case_insensitive",
            ),
            # RFC 8141 compliance - newly allowed characters (tilde, ampersand)
            pytest.param(
                "urn:syntara:resource~1",
                "urn:syntara:resource~1",
                None,
                id="valid_urn_with_tilde",
            ),
            pytest.param(
                "urn:syntara:a&b",
                "urn:syntara:a&b",
                None,
                id="valid_urn_with_ampersand",
            ),
            pytest.param(
                "urn:example:data~backup&filter",
                "urn:example:data~backup&filter",
                None,
                id="valid_urn_with_tilde_and_ampersand",
            ),
            # Max length validation (1024 chars)
            pytest.param(
                "urn:syntara:" + "x" * 1012,  # Total = 12 + 1012 = 1024
                "urn:syntara:" + "x" * 1012,
                None,
                id="valid_urn_at_max_length_1024",
            ),
            # None and omitted values - should result in None
            pytest.param(None, None, None, id="none_value_accepted"),
            # Invalid URNs - should be dropped with warnings
            pytest.param(
                "syntara:workflow:123",
                None,
                "does not conform to RFC 8141",
                id="invalid_missing_urn_prefix",
            ),
            pytest.param("urn:syntara", None, "does not conform to RFC 8141", id="invalid_missing_nss"),
            pytest.param("urn:a:resource", None, "does not conform to RFC 8141", id="invalid_nid_too_short"),
            pytest.param(
                "urn:this-is-a-very-long-namespace-identifier-over-thirty-two-chars:resource",
                None,
                "does not conform to RFC 8141",
                id="invalid_nid_too_long",
            ),
            pytest.param("", None, "does not conform to RFC 8141", id="invalid_empty_string"),
            pytest.param(12345, None, "must be a string", id="invalid_wrong_type"),
            pytest.param("invalid-urn-format", None, "does not conform to RFC 8141", id="invalid_format"),
            # RFC 8141 compliance - hash is a fragment delimiter and not allowed in NSS
            pytest.param(
                "urn:syntara:resource#fragment",
                None,
                "does not conform to RFC 8141",
                id="invalid_urn_with_hash_fragment",
            ),
        ],
    )
    def test_resource_urn_validation(
        self,
        input_urn: Any,  # noqa: ANN401
        expected_urn: str | None,
        expected_log_fragment: str | None,
    ) -> None:
        """Test resource_urn RFC 8141 validation with various inputs."""
        with patch("syntara.audit.models.audit_event.logger") as mock_logger:
            # Create event with the input URN (or omit if None and testing omission)
            event = AuditEvent(
                event_category=EventCategory.USER_ACTION,
                event_action="test",
                source_component="test",
                resource_urn=input_urn if input_urn is not None else None,
                event_message="test",
                structured_data=AuditContextData(data_type="test"),
            )

            # Verify the URN is set to the expected value
            assert event.resource_urn == expected_urn

            # Verify expected log message if provided
            if expected_log_fragment:
                # Check that logger.warning was called
                assert mock_logger.warning.called
                # Get the first positional argument (the log message)
                call_args = mock_logger.warning.call_args
                log_message = call_args[0][0] if call_args[0] else ""
                assert expected_log_fragment in log_message

    def test_resource_urn_max_length_validation(self) -> None:
        """Test that resource_urn exceeding 1024 characters raises ValidationError."""
        # URN exceeding max_length should raise ValidationError from Pydantic
        with pytest.raises(ValidationError) as exc_info:
            AuditEvent(
                event_category=EventCategory.USER_ACTION,
                event_action="test",
                source_component="test",
                resource_urn="urn:syntara:" + "x" * 1015,  # Total = 1027 chars (exceeds 1024)
                event_message="test",
                structured_data=AuditContextData(data_type="test"),
            )

        # Verify the error is specifically about string length
        error = exc_info.value.errors()[0]
        assert error["type"] == "string_too_long"
        assert error["loc"] == ("resource_urn",)


class TestAuditEventResourceNameValidation:
    """Tests for resource_name validation."""

    def test_resource_name_is_optional(self) -> None:
        """Test that resource_name can be omitted."""
        event = AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="test",
            source_component="test",
            event_message="test",
            structured_data=AuditContextData(data_type="test"),
        )

        assert event.resource_name is None

    def test_resource_name_accepts_valid_name(self) -> None:
        """Test that resource_name accepts a valid name."""
        event = AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="test",
            source_component="test",
            resource_name="test-workflow",
            event_message="test",
            structured_data=AuditContextData(data_type="test"),
        )

        assert event.resource_name == "test-workflow"

    def test_resource_name_max_length_validation(self) -> None:
        """Test that resource_name exceeding 255 characters raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AuditEvent(
                event_category=EventCategory.USER_ACTION,
                event_action="test",
                source_component="test",
                resource_name="x" * 256,  # Exceeds 255
                event_message="test",
                structured_data=AuditContextData(data_type="test"),
            )

        # Verify the error is specifically about string length
        error = exc_info.value.errors()[0]
        assert error["type"] == "string_too_long"
        assert error["loc"] == ("resource_name",)
