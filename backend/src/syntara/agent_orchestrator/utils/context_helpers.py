"""Helper functions for extracting data from InvocationContextData."""

import contextlib
from typing import Any
from uuid import UUID

from syntara.agent_orchestrator.models import InvocationContextData


def extract_workflow_id(ctx: InvocationContextData) -> UUID | None:
    """Extract workflow_id UUID from invocation context.

    Args:
        ctx: Invocation context data containing workflow metadata

    Returns:
        UUID if workflow_id exists and is valid, None otherwise

    """
    if ctx.workflow_id:
        with contextlib.suppress(ValueError):
            return UUID(ctx.workflow_id)
    return None


def extract_execution_id(ctx: InvocationContextData) -> UUID | None:
    """Extract execution_id UUID from invocation context.

    Args:
        ctx: Invocation context data containing execution metadata

    Returns:
        UUID if execution_id exists and is valid, None otherwise

    """
    if ctx.execution_id:
        with contextlib.suppress(ValueError):
            return UUID(ctx.execution_id)
    return None


def extract_request_id(ctx: InvocationContextData) -> UUID | None:
    """Extract request_id UUID from invocation context.

    The request_id is stored in the metadata section of the invocation context
    and represents the originating HTTP request's X-Request-Id header value.

    Args:
        ctx: Invocation context data containing request metadata

    Returns:
        UUID if request_id exists in metadata and is valid, None otherwise

    """
    if ctx.metadata and ctx.metadata.request_id:
        with contextlib.suppress(ValueError):
            return UUID(ctx.metadata.request_id)
    return None


def extract_response_schema(ctx: InvocationContextData) -> dict[str, Any] | None:
    """Extract response_schema from invocation context.

    The response schema defines the expected structure of the agent's response
    and is stored as an opaque object in the metadata section.

    Args:
        ctx: Invocation context data containing response schema metadata

    Returns:
        Dictionary representing the response schema if it exists, None otherwise

    """
    opaque = ctx.metadata.response_schema if ctx.metadata else None
    return opaque.get_data() if opaque else None
