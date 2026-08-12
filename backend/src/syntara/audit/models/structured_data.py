"""Structured data schemas for audit events."""

from sqlmodel import Field, SQLModel


class AuditContextData(SQLModel):
    """Universal structured data for all audit events.

    Accepts arbitrary extra fields so callers may pass domain-specific context.
    All audit events use this single structured data type.

    The data_type field serves as a discriminator for UI/frontend purposes,
    allowing different audit event types to be distinguished and rendered appropriately.
    """

    data_type: str = Field(description="Discriminator identifying the audit event type")
    error_type: str | None = Field(default=None, description="Type of error if an error occurred")
    error_message: str | None = Field(default=None, description="Detailed error message if an error occurred")

    model_config = {"extra": "allow"}
