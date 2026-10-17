"""Sanitized content failures, without acknowledgement or commit semantics."""

from enum import StrEnum

from sqlmodel import SQLModel


class EventFailureCode(StrEnum):
    """Stable categories for a caller's per-message audit event."""

    tombstone = "tombstone"
    invalid_utf8 = "invalid_utf8"
    invalid_json = "invalid_json"
    duplicate_member = "duplicate_member"
    non_finite_number = "non_finite_number"
    excessive_nesting = "excessive_nesting"
    malformed_content_type = "malformed_content_type"
    duplicate_content_type = "duplicate_content_type"
    unsupported_content_type = "unsupported_content_type"
    registry_framing = "registry_framing"
    value_too_large = "value_too_large"
    envelope_too_large = "envelope_too_large"
    invalid_schema = "invalid_schema"
    schema_mismatch = "schema_mismatch"


_FAILURE_MESSAGES = {
    EventFailureCode.tombstone: "A null source value is not a JSON event.",
    EventFailureCode.invalid_utf8: "The event value is not valid UTF-8.",
    EventFailureCode.invalid_json: "The event value is not valid JSON.",
    EventFailureCode.duplicate_member: "A JSON object contains duplicate member names.",
    EventFailureCode.non_finite_number: "The event contains a non-finite JSON number.",
    EventFailureCode.excessive_nesting: "Event nesting exceeds decoder capacity.",
    EventFailureCode.malformed_content_type: "The content-type header is malformed.",
    EventFailureCode.duplicate_content_type: "Multiple content-type headers are not supported.",
    EventFailureCode.unsupported_content_type: "The declared content type or charset is not supported.",
    EventFailureCode.registry_framing: "Schema-registry binary framing is not supported.",
    EventFailureCode.value_too_large: "The event value exceeds the configured candidate byte limit.",
    EventFailureCode.envelope_too_large: "The encoded envelope exceeds the configured candidate byte limit.",
    EventFailureCode.invalid_schema: "The payload schema is invalid or contains an unsafe construct.",
    EventFailureCode.schema_mismatch: "The payload does not satisfy its schema.",
}


class EventDecodeFailure(SQLModel):
    """Safe result for the caller to audit; never proof of durable resolution."""

    code: EventFailureCode

    @property
    def message(self) -> str:
        """Return a fixed description without any source or exception contents."""
        return _FAILURE_MESSAGES[self.code]
