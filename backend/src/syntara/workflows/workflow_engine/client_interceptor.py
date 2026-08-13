"""Temporal client interceptor that injects workflow auth headers.

Automatically signs every ``start_workflow`` call with an HMAC token
so the worker-side auth interceptor can verify the request originated
from an authorized process.
"""

from __future__ import annotations

from typing import Any

from temporalio.api.common.v1 import Payload
from temporalio.client import (
    Interceptor,
    OutboundInterceptor,
    StartWorkflowInput,
    WorkflowHandle,
)

from syntara.workflows.workflow_engine.workflow_auth import HEADER_NAME, sign_workflow


class _WorkflowAuthOutboundInterceptor(OutboundInterceptor):
    """Outbound interceptor that adds HMAC auth headers to workflow starts."""

    async def start_workflow(self, input: StartWorkflowInput) -> WorkflowHandle[Any, Any]:  # noqa: A002
        headers = dict(input.headers)
        headers[HEADER_NAME] = Payload(data=sign_workflow(input.id, input.workflow, input.args))
        input.headers = headers
        return await self.next.start_workflow(input)


class WorkflowAuthClientInterceptor(Interceptor):
    """Client interceptor that signs workflow submissions with HMAC."""

    def intercept_client(self, next: OutboundInterceptor) -> OutboundInterceptor:  # noqa: A002
        """Return outbound interceptor that injects auth headers."""
        return _WorkflowAuthOutboundInterceptor(next)
