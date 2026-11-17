"""Form field error model for validation results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormFieldError:
    """A single form field validation error.

    Carries structured per-field error information for client-side rendering.

    Codes produced when submitting form:

    - ``required`` - no value supplied for a required field
    - ``type`` - value is the wrong Python type
    - ``invalid_format`` - invalid format of data
    - ``not_in_options`` - value is absent from a static option list
    - ``must_be_checked`` - a required checkbox was not ticked
    - ``unknown_field`` - submitted key is not defined in the form

    Codes produced when creating form definition:

    - ``invalid_default`` - a field default the submission coercer would reject

    Attributes:
        field: Field name from the descriptor
        label: Display label from the descriptor
        code: One of the codes above
        message: User-facing error message

    """

    field: str
    label: str
    code: str
    message: str
