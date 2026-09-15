"""Unit-test-only helper functions for creating in-memory form prompt instances."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from syntara.forms.models import FormPrompt, FormPromptStatus


def create_test_form_prompt(
    execution_id: UUID | None = None,
    prompt_node_id: str = "test_prompt",
    name: str = "Test Form Prompt",
    message: str | None = None,
    status: FormPromptStatus = FormPromptStatus.PENDING,
    timeout_at: datetime | None = None,
    responded_by: UUID | None = None,
    responded_at: datetime | None = None,
    response_data: dict[str, Any] | None = None,
) -> FormPrompt:
    """Create a FormPrompt in memory with sensible defaults for unit tests."""
    if execution_id is None:
        execution_id = uuid4()

    if timeout_at is None and status == FormPromptStatus.PENDING:
        timeout_at = datetime.now(UTC) + timedelta(days=1)

    return FormPrompt(
        execution_id=execution_id,
        project_id=uuid4(),
        prompt_node_id=prompt_node_id,
        name=name,
        message=message,
        status=status,
        timeout_at=timeout_at,
        input_schema={"type": "object", "properties": {"reason": {"type": "string"}}},
        responded_by=responded_by,
        responded_at=responded_at,
        response_data=response_data,
    )


def create_submitted_form_prompt(
    responded_by: UUID | None = None,
    response_data: dict[str, Any] | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> FormPrompt:
    """Create a submitted FormPrompt with defaults."""
    if responded_by is None:
        responded_by = uuid4()

    if response_data is None:
        response_data = {"reason": "Test submission"}

    return create_test_form_prompt(
        status=FormPromptStatus.SUBMITTED,
        responded_by=responded_by,
        responded_at=datetime.now(UTC),
        response_data=response_data,
        timeout_at=None,  # Submitted prompts don't need timeout
        **kwargs,
    )
