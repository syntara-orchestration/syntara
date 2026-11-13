"""Credential-reference resolution for Execution Plane commands."""

from typing import TYPE_CHECKING
from uuid import UUID

from execution_plane_client.commands.base import CommandPayload
from execution_plane_client.commands.credentials import CredentialResolve, CredentialResolveWorkload
from execution_plane_client.commands.results import (
    CredentialResolveCommandResult,
    CredentialResolveWorkloadCommandResult,
)
from execution_plane_client.errors import ProtocolConflict
from execution_plane_client.handlers import HandlingResult
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from pydantic import ValidationError
from sqlalchemy.orm import selectinload
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.lib.encryption import EncryptionError
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandResourceNotFoundError, CommandResourceStateError
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_definition import WorkflowDefinition, WorkflowNode

if TYPE_CHECKING:
    from syntara.workflows.workflow_engine.models.workflow_definition import CredentialBinding


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
    ) -> HandlingResult:
        """Return a correlated credential value without exposing resolution details."""
        del message
        if not isinstance(payload, CredentialResolve):
            raise ProtocolConflict
        credential = await self._resolve_credential(context.session, payload.credential_ref)
        return HandlingResult(
            resource=None,
            result=CredentialResolveCommandResult(credential=credential),
        )


class CredentialResolveWorkloadCommandHandler:
    """Resolve one credential for the active work item identified by work_item_id."""

    async def _load_activity(self, session: AsyncSession, work_item_id: UUID) -> ActivityExecution | None:
        """Load the activity and its execution/workflow version in one query."""
        result = await session.exec(
            select(ActivityExecution)
            .where(col(ActivityExecution.id) == work_item_id)
            .options(
                selectinload(ActivityExecution.execution).selectinload(Execution.workflow_version),  # type: ignore[arg-type]
            )
        )
        return result.one_or_none()

    def _node_for_activity(self, activity: ActivityExecution) -> WorkflowNode:
        """Return the workflow node whose deterministic UUID matches the activity."""
        execution = activity.execution
        workflow_version = execution.workflow_version
        try:
            definition = WorkflowDefinition.model_validate(workflow_version.workflow_definition)
        except ValidationError as error:
            raise CommandResourceStateError from error
        for node in definition.nodes:
            if execution_plane_work_item_id(execution.id, node.id) == activity.id:
                return node
        raise CommandResourceStateError

    def _binding_matches(self, node: WorkflowNode, payload: CredentialResolveWorkload) -> bool:
        """Check whether the requested recipe and reference are bound to the node."""
        bindings: list[CredentialBinding] = getattr(node.parameters, "credential_bindings", [])
        return any(
            binding.credential_recipe_id == payload.credential_recipe_id
            and binding.credential_ref == payload.credential_ref
            for binding in bindings
        )

    async def _resolve_credential_document(
        self,
        session: AsyncSession,
        credential_ref: UUID,
        project_id: UUID,
    ) -> dict[str, str]:
        """Resolve a project-scoped credential into a flat string document."""
        try:
            credential, credential_type = await fetch_credential_with_type(session, credential_ref)
        except IntegrationCredentialNotFoundError as error:
            raise CommandResourceStateError from error
        if credential.project_id != project_id or not credential.enabled:
            raise CommandResourceStateError
        secret_service = create_secret_service(session)
        try:
            secret_data = await secret_service.retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
        except (EncryptionError, KeyError) as error:
            raise CommandResourceStateError from error
        resolved = InjectorResolver.resolve(credential_type.injectors or {}, secret_data).extra_vars
        document = {str(key): str(value) for key, value in resolved.items() if value is not None}
        if not document:
            raise CommandResourceStateError
        return document

    async def handle(
        self,
        message: MessageEnvelope,
        payload: CommandPayload,
        context: AOCommandContext,
    ) -> HandlingResult:
        """Resolve a credential only after validating its work-item binding."""
        del message
        if not isinstance(payload, CredentialResolveWorkload):
            raise ProtocolConflict
        work_item_id = payload.work_item_id
        activity = await self._load_activity(context.session, work_item_id)
        if activity is None:
            raise CommandResourceNotFoundError
        if activity.status in TERMINAL_ACTIVITY_STATUSES:
            raise CommandResourceStateError
        node = self._node_for_activity(activity)
        if not self._binding_matches(node, payload):
            raise CommandResourceStateError
        credential = await self._resolve_credential_document(
            context.session,
            payload.credential_ref,
            activity.execution.project_id,
        )
        return HandlingResult(
            resource=ResourceReference(kind="work_item", resource_id=work_item_id),
            result=CredentialResolveWorkloadCommandResult(credential=credential),
        )
