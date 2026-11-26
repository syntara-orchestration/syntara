"""Credential-reference resolution for Execution Plane commands."""

from typing import TYPE_CHECKING
from uuid import UUID

from execution_plane_client.commands.base import CommandPayload
from execution_plane_client.commands.credentials import CredentialResolveCluster, CredentialResolveWorkload
from execution_plane_client.commands.results import (
    CredentialResolveClusterCommandResult,
    CredentialResolveWorkloadCommandResult,
)
from execution_plane_client.errors import ProtocolConflict
from execution_plane_client.handlers import HandlingResult
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from pydantic import ValidationError
from sqlalchemy.orm import selectinload
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.lib.encryption import EncryptionError
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.audit.credential import CredentialClusterResolvedEvent, CredentialWorkloadResolvedEvent
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandResourceNotFoundError, CommandResourceStateError
from syntara.execution_plane.registry.repository import (
    execution_plane_plugin_credential_recipe_ids,
    get_execution_plane_plugin_by_node_type,
)
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type
from syntara.workflow_core.models import NodeType
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_definition import WorkflowDefinition, WorkflowNode

if TYPE_CHECKING:
    from syntara.workflow_core.models import CredentialBinding


class CredentialResolveClusterCommandHandler:
    """Resolve one opaque cluster credential reference into its credential document."""

    async def _load_integration(self, session: AsyncSession, resource_id: UUID) -> Integration | None:
        """Load the Integration that owns the requesting Execution Plane Cluster."""
        result = await session.exec(select(Integration).where(col(Integration.id) == resource_id))
        return result.one_or_none()

    async def _resolve_credential_document(self, session: AsyncSession, credential_ref: UUID) -> dict[str, str]:
        """Resolve an AO credential reference without logging or persisting its values."""
        try:
            credential, credential_type = await fetch_credential_with_type(session, credential_ref)
        except IntegrationCredentialNotFoundError as error:
            raise CommandResourceStateError from error
        if not credential.enabled:
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
        self, message: MessageEnvelope, payload: CommandPayload, context: AOCommandContext
    ) -> HandlingResult:
        """Return a correlated credential document without exposing resolution details."""
        if not isinstance(payload, CredentialResolveCluster):
            raise ProtocolConflict
        integration = await self._load_integration(context.session, payload.resource_id)
        if (
            integration is None
            or integration.integration_type != IntegrationType.OPENSHIFT
            or integration.management_credential_id != payload.credential_ref
            or not integration.enabled
        ):
            raise CommandResourceStateError
        credential = await self._resolve_credential_document(context.session, payload.credential_ref)
        AuditEventDispatcher.dispatch(
            CredentialClusterResolvedEvent(
                credential_id=payload.credential_ref,
                integration_id=payload.resource_id,
                message_id=message.message_id,
                service_identity=message.source_id,
            )
        )
        return HandlingResult(
            resource=ResourceReference(kind="cluster", resource_id=payload.resource_id),
            result=CredentialResolveClusterCommandResult(credential=credential),
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

    async def _recipe_is_plugin_reachable(self, session: AsyncSession, node: WorkflowNode, recipe_id: str) -> bool:
        """Check whether the node's plugin can request the bound recipe."""
        plugin = await get_execution_plane_plugin_by_node_type(session, NodeType(node.type))
        if plugin is None:
            return False
        try:
            recipe_ids = await execution_plane_plugin_credential_recipe_ids(session, plugin)
        except ValueError:
            return False
        return recipe_id in recipe_ids

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
        if not await self._recipe_is_plugin_reachable(context.session, node, payload.credential_recipe_id):
            raise CommandResourceStateError
        credential = await self._resolve_credential_document(
            context.session,
            payload.credential_ref,
            activity.execution.project_id,
        )
        AuditEventDispatcher.dispatch(
            CredentialWorkloadResolvedEvent(
                credential_id=payload.credential_ref,
                work_item_id=work_item_id,
                message_id=message.message_id,
                service_identity=message.source_id,
            )
        )
        return HandlingResult(
            resource=ResourceReference(kind="work_item", resource_id=work_item_id),
            result=CredentialResolveWorkloadCommandResult(credential=credential),
        )
