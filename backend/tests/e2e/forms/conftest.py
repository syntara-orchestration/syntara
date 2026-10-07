"""Fixtures for cleaning up form-prompt E2E executions."""

from collections.abc import Callable, Generator
from uuid import UUID

import pytest
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowRead

from ._helpers import cancel_form_prompt_execution


@pytest.fixture
def form_prompt_execution_cleanup(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
) -> Generator[Callable[[UUID], None], None, None]:
    """Cancel executions started by a form-prompt E2E before workflow teardown."""
    _ = workflow_factory  # Ensure this finalizer runs before workflow_factory deletes its workflows.
    execution_ids: list[UUID] = []
    yield execution_ids.append

    cleanup_errors: list[str] = []
    for execution_id in reversed(execution_ids):
        try:
            cancel_form_prompt_execution(syntara_api, execution_id)
        except Exception as exc:
            cleanup_errors.append(f"{execution_id}: {exc!r}")
    if cleanup_errors:
        pytest.fail("Failed to clean up form-prompt executions: " + "; ".join(cleanup_errors), pytrace=False)
