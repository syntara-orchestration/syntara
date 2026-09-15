"""Form field error model for validation results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormFieldError:
    """A single form field validation error.

    Carries structured per-field error information for client-side rendering.
    """

    field: str  # Field name from the descriptor
    label: str  # Display label from the descriptor
    code: str  # Error code: "required" | "type" | "unknown_field" | "not_in_options" | "must_be_checked"
    message: str  # User-facing error message
