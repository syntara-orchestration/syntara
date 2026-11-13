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

from syntara.authz.dependencies import get_authz_evaluator
from syntara.authz.engine import AuthzRequest, authorize
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.models.principal import service_principal_id
from syntara.core.syntara_router import SyntaraRouter
from syntara.execution_plane.client import EP_AUDIENCE, EP_CLIENT_ID
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import (
    CommandDependencyUnavailableError,
    CommandResourceNotFoundError,
    CommandResourceStateError,
)
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

_COMMAND_ACTIONS = {
    "work.execute.completed": "complete",
    "credential.resolve": "resolve-credential",
    "credential.resolve.workload": "resolve-credential-workload",
}


class ExecutionPlaneCallbackIdentity:
    """Require the Execution Plane's mTLS and protocol identities."""

    async def __call__(self, request: Request, message: MessageEnvelope) -> None:
        """Reject requests that do not present every required EP identity."""
        settings = get_settings()
        if (
            not getattr(request.state, "is_cert_authenticated", False)
            or getattr(request.state, "cert_cn", None) != settings.ep_callback_service_cn
            or message.source_id != EP_AUDIENCE
            or message.destination_id != EP_CLIENT_ID
            or message.scope.client_id != EP_CLIENT_ID
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Execution Plane service identity required"
            )


_execution_plane_callback_identity = ExecutionPlaneCallbackIdentity()


async def _authorize_execution_plane_command(request: Request, session: AsyncSession, message: MessageEnvelope) -> None:
    """Authorize one validated callback command for the EP service principal."""
    action = _COMMAND_ACTIONS.get(message.command.command_type)
    if action is None:
        raise UnsupportedCommand

    authz_request = AuthzRequest(
        user_id=service_principal_id(request.state.cert_cn),
        action=action,
        resource_type="execution-plane-callback",
        resource_id=str(message.message_id),
        groups=[],
    )
    result = await authorize(session, get_authz_evaluator(request), authz_request)
    if not result.allowed:
        denial_message = "Execution Plane callback denied"
        raise AuthorizationDeniedError(denial_message)


@router.post(
    "/commands",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_execution_plane_callback_identity)],
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
    try:
        payload = catalog.validate(message)
        handler = registry.get(message.command.command_type, message.command.command_revision)
        await _authorize_execution_plane_command(request, session, message)
        handled = await handler.handle(message, payload, AOCommandContext(session, temporal_service))
    except CommandDependencyUnavailableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Temporal is unavailable") from None
    except CommandResourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No matching AO activity for this work item"
        ) from None
    except CommandResourceStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Work item is not eligible for credential resolution"
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
