"""Authenticated AO ingress for Execution Plane commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from execution_plane_client.catalog import CommandCatalog
from execution_plane_client.commands.results import TransportReceipt
from execution_plane_client.errors import ProtocolConflict, UnsupportedCommand
from execution_plane_client.protocol import MessageEnvelope  # noqa: TC002 — FastAPI resolves this body annotation.
from fastapi import Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: TC002 — FastAPI resolves dependency annotations

from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.execution_plane.client import EP_AUDIENCE, EP_CLIENT_ID
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandDependencyUnavailableError, CommandResourceNotFoundError
from syntara.execution_plane.commands.registry import build_ao_registry
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.workflow_engine.services.temporal_execution_service import (
    TemporalExecutionService,  # noqa: TC001 — FastAPI resolves dependency annotations
)

if TYPE_CHECKING:
    from execution_plane_client.handlers import HandlingResult

router = SyntaraRouter(prefix="/api/execution_plane/v1", tags=["Execution Plane"])
catalog = CommandCatalog()
registry = build_ao_registry()


@router.post(
    "/commands",
    status_code=status.HTTP_200_OK,
    dependencies=[NO_PERMISSION],
    include_in_schema=False,
    operation_id="receive_execution_plane_command",
    summary="Receive an Execution Plane command",
)
async def receive_execution_plane_command(
    request: Request,
    message: MessageEnvelope,
    session: Annotated[AsyncSession, Depends(get_db)],
    temporal_service: Annotated[TemporalExecutionService | None, Depends(get_temporal_execution_service)],
) -> TransportReceipt:
    """Authenticate one command, dispatch it through the registry, and return its result."""
    settings = get_settings()
    if (
        not getattr(request.state, "is_cert_authenticated", False)
        or getattr(request.state, "cert_cn", None) != settings.ep_callback_service_cn
        or message.source_id != EP_AUDIENCE
        or message.destination_id != EP_CLIENT_ID
        or message.scope.client_id != EP_CLIENT_ID
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Execution Plane service identity required")
    try:
        payload = catalog.validate(message)
        handler = registry.get(message.command.command_type, message.command.command_revision)
        handled = await handler.handle(message, payload, AOCommandContext(session, temporal_service))
    except CommandDependencyUnavailableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Temporal is unavailable") from None
    except CommandResourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No matching AO activity for this work item"
        ) from None
    except (ValidationError, UnsupportedCommand, ProtocolConflict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid command") from None
    return _transport_receipt(message, handled)


def _transport_receipt(message: MessageEnvelope, handled: HandlingResult) -> TransportReceipt:
    """Normalize one participant result into the shared receipt contract."""
    return TransportReceipt(
        message_id=message.message_id,
        resource=handled.resource,
        result=handled.result,
    )
