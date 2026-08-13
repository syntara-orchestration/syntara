"""Worker interceptor that validates workflow authorization headers.

Rejects any workflow execution that was not submitted by an authorized
process (the API or scheduler). Child workflows are trusted because
the ``parent`` field in ``workflow.info()`` is set by the Temporal
server and cannot be forged by an external client.
"""

from typing import Any

import structlog
from temporalio import workflow
from temporalio.exceptions import ApplicationError
from temporalio.worker import (
    ExecuteWorkflowInput,
    Interceptor,
    WorkflowInboundInterceptor,
    WorkflowInterceptorClassInput,
)

with workflow.unsafe.imports_passed_through():
    from syntara.workflows.workflow_engine.workflow_auth import HEADER_NAME, verify_workflow

logger = structlog.stdlib.get_logger(__name__)


class _WorkflowAuthInboundInterceptor(WorkflowInboundInterceptor):
    """Inbound interceptor that validates HMAC auth headers on workflow start."""

    async def execute_workflow(self, input: ExecuteWorkflowInput) -> Any:  # noqa: A002, ANN401
        info = workflow.info()

        # Child workflows inherit trust from their already-validated parent.
        # The parent field is set by the Temporal server based on the actual
        # workflow call graph and cannot be faked by an external client.
        if info.parent is None:
            auth_payload = input.headers.get(HEADER_NAME)
            if auth_payload is None or not verify_workflow(
                info.workflow_id, info.workflow_type, input.args, auth_payload.data
            ):
                logger.warning(
                    "Rejected unauthorized workflow execution",
                    workflow_id=info.workflow_id,
                    workflow_type=info.workflow_type,
                    has_auth_header=auth_payload is not None,
                )
                msg = f"Unauthorized workflow execution: {info.workflow_type}"
                raise ApplicationError(msg, non_retryable=True)

        return await super().execute_workflow(input)


class WorkflowAuthInterceptor(Interceptor):
    """Worker interceptor that enforces workflow submission authorization."""

    def workflow_interceptor_class(
        self,
        input: WorkflowInterceptorClassInput,  # noqa: A002, ARG002
    ) -> type[WorkflowInboundInterceptor]:
        """Return the workflow auth inbound interceptor class."""
        return _WorkflowAuthInboundInterceptor
