"""Credential-reference resolution for Execution Plane commands."""

from uuid import UUID

from execution_plane_client.commands.base import CommandPayload
from execution_plane_client.commands.credentials import CredentialResolution, CredentialResolve
from execution_plane_client.errors import ProtocolConflict
from execution_plane_client.protocol import MessageEnvelope
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.results import AOCommandResult
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type


class CredentialResolveCommandHandler:
    """Resolve one opaque credential reference into its typed value."""

    async def _resolve_credential(self, session: AsyncSession, credential_ref: UUID) -> str:
        """Resolve an AO credential reference without logging or persisting its value."""
        credential, credential_type = await fetch_credential_with_type(session, credential_ref)
        if not credential.enabled:
            message = "Credential is disabled"
            raise ValueError(message)
        secret_service = create_secret_service(session)
        secret_data = await secret_service.retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
        resolved = InjectorResolver.resolve(credential_type.injectors or {}, secret_data).extra_vars
        secret = str(resolved.get("bearer_token") or resolved.get("token") or resolved.get("api_key") or "")
        if not secret:
            message = "Credential did not resolve to an API token"
            raise ValueError(message)
        return secret

    async def handle(
        self, message: MessageEnvelope, payload: CommandPayload, context: AOCommandContext
    ) -> AOCommandResult:
        """Return a correlated credential value without exposing resolution details."""
        if not isinstance(payload, CredentialResolve):
            raise ProtocolConflict
        credential = await self._resolve_credential(context.session, payload.credential_ref)
        return AOCommandResult(
            resource=None,
            body=CredentialResolution(message_id=message.message_id, credential=credential),
        )
