"""Form-trigger validation and observability.

``record_form_trigger_submission`` is fire-and-forget: observability failures
must never fail a submission.
"""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Any, NamedTuple

import structlog
from pydantic import ValidationError

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import request_id_context_var
from syntara.forms.exceptions import FormDataValidationError
from syntara.forms.models.form_fields import DynamicOptions, FormDefinition, ResolvedOptions
from syntara.forms.validators.submission import validate_form_submission
from syntara.metrics.types import ComponentLabel, MetricType
from syntara.workflows.audit.form_trigger import FormTriggerSubmittedEvent
from syntara.workflows.exceptions import TriggerValidationError

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from syntara.core.models import User
    from syntara.metrics.recorder import MetricsRecorder

logger = structlog.stdlib.get_logger(__name__)


class FormSchemaSummary(NamedTuple):
    """Field metadata from a form trigger definition, for observability only.

    ``field_count`` is the number of fields in the form definition.
    """

    field_types: list[str]
    field_count: int


def validate_form_trigger_submission(
    trigger_node: dict[str, Any],
    input_data: dict[str, Any],
    *,
    workflow_id: UUID | None = None,
) -> tuple[dict[str, Any], FormSchemaSummary]:
    """Validate and normalize a form-trigger submission.

    Returns the cleaned input data and its schema summary. The cleaned values
    use the same shape as form prompt submissions. Form Triggers additionally
    reject dynamic options because they have no upstream values from which to
    resolve them.
    """
    trigger_node_id = trigger_node.get("id")
    validation_context = {
        "workflow_id": workflow_id,
        "request_id": request_id_context_var.get(),
        "trigger_node_id": trigger_node_id,
    }
    raw_parameters = trigger_node.get("parameters")
    raw_form_definition = raw_parameters.get("form_definition") if isinstance(raw_parameters, dict) else None
    try:
        form_definition = FormDefinition.model_validate(raw_form_definition)
    except ValidationError as exc:
        error_count = len(exc.errors())
        logger.warning(
            "Form trigger has an invalid form definition",
            error_type=type(exc).__name__,
            error_count=error_count,
            **validation_context,
        )
        msg = "Form trigger has an invalid form definition"
        raise TriggerValidationError(msg) from None

    if any(
        isinstance(getattr(field, "options", None), (DynamicOptions, ResolvedOptions))
        for field in form_definition.fields
    ):
        logger.error("Form trigger has unsupported dynamic options", **validation_context)
        msg = "Form trigger form definition contains unsupported dynamic options"
        raise TriggerValidationError(msg)

    try:
        cleaned_input = validate_form_submission(form_definition, input_data)
        field_types = sorted({str(field.type) for field in form_definition.fields})
        return cleaned_input, FormSchemaSummary(
            field_types=field_types,
            field_count=len(form_definition.fields),
        )
    except FormDataValidationError as exc:
        logger.warning(
            "Form trigger submission validation failed",
            error_count=len(exc.errors),
            **validation_context,
        )
        # Re-raise with the trigger node id attached for log/diagnostic context.
        raise FormDataValidationError(exc.errors, form_id=trigger_node_id) from exc


def record_form_trigger_submission(
    *,
    recorder: MetricsRecorder,
    user: User,
    submission_started: float,
    submitted_at: datetime,
    workflow_id: UUID,
    workflow_name: str,
    execution_id: UUID,
    trigger_node_id: str,
    form_schema: FormSchemaSummary,
) -> None:
    """Record submission latency and dispatch the metadata-only audit event."""
    try:
        try:
            recorder.record(
                MetricType.FORM_TRIGGER_SUBMISSION_START,
                (monotonic() - submission_started) * 1000,
                unit="ms",
                component=ComponentLabel.EXECUTION_SERVICE,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to record form trigger submission start metric (non-fatal)", exc_info=True)

        AuditEventDispatcher.dispatch(
            FormTriggerSubmittedEvent(
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                execution_id=execution_id,
                trigger_node_id=trigger_node_id,
                submitted_by=user.id,
                submitted_at=submitted_at,
                field_count=form_schema.field_count,
                field_types=form_schema.field_types,
                principal_type=user.__dict__.get("__principal_type__"),
            )
        )
    except Exception:  # noqa: BLE001
        logger.warning("Form trigger submission observability failed (non-fatal)", exc_info=True)
