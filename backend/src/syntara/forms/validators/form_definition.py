"""Form definition validation.

Validates a form definition by checking that the form field
default values can be submitted without error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from syntara.forms.exceptions import FormDefinitionError
from syntara.forms.models.form_errors import FormFieldError
from syntara.forms.validators.submission import coerce_field

if TYPE_CHECKING:
    from syntara.forms.models.form_fields import FormDefinition


def validate_form_definition(form: FormDefinition, form_id: str | None = None) -> None:
    """Check that every field default is usable by the coercer during submission.

    Args:
        form: The form definition to check
        form_id: Optional form/node identifier for error context

    Raises:
        FormDefinitionError: If any default is invalid (carries all field errors)

    """
    errors: list[FormFieldError] = []

    for field in form.fields:
        # A checkbox default is a concrete bool, never None, and is covered by
        # the model's own typing; every other field treats None as "no default".
        if field.default is None:
            continue

        try:
            coerce_field(field, field.default)
        except (TypeError, ValueError) as exc:
            errors.append(
                FormFieldError(
                    field=field.value_name,
                    label=field.label,
                    code="invalid_default",
                    message=f"Default value is not valid for a '{field.type}' field: {exc}",
                )
            )

    if errors:
        raise FormDefinitionError(errors, form_id)
