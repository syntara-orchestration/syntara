"""Service for managing webhook trigger registrations.

Webhook triggers are auto-synced from workflow definitions. This service handles
the lookup table CRUD and payload validation. Supports multiple trigger types
(webhook_trigger, eda_trigger) via the ``trigger_type`` discriminator.
"""

import re
from typing import Any
from uuid import UUID, uuid4

import structlog
from pydantic import ValidationError
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.service_accounts.models.service_account import ServiceAccount
from syntara.workflows.exceptions import (
    TriggerValidationError,
    WebhookServiceAccountNotAuthorizedError,
    WebhookTriggerNotFoundError,
    WebhookTriggerPathConflictError,
)
from syntara.workflows.models.webhook_trigger import WebhookTrigger, WebhookTriggerRead
from syntara.workflows.models.webhook_trigger_service_account import WebhookTriggerServiceAccount
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, WebhookTriggerParameters

logger = structlog.stdlib.get_logger(__name__)

_UNKNOWN = "<unknown>"

WEBHOOK_TRIGGER_TYPES: tuple[str, ...] = (
    NodeType.WEBHOOK_TRIGGER,
    NodeType.EDA_TRIGGER,
)


class WebhookTriggerService(BaseService):
    """Service for managing the webhook trigger lookup table.

    Webhook triggers are derived from workflow definitions. This service
    synchronises the lookup table when workflows are created, updated, or deleted.
    """

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize WebhookTriggerService."""
        super().__init__(session, user)

    async def verify_service_account_authorization(
        self,
        trigger_id: UUID,
        service_account_id: UUID,
    ) -> None:
        """Verify that a service account is authorized to invoke a trigger.

        Args:
            trigger_id: The webhook trigger ID.
            service_account_id: The service account ID from the Bearer token.

        Raises:
            WebhookServiceAccountNotAuthorizedError: If the SA is not bound to the trigger.

        """
        result = await self.session.exec(
            select(WebhookTriggerServiceAccount).where(
                WebhookTriggerServiceAccount.webhook_trigger_id == trigger_id,
                WebhookTriggerServiceAccount.service_account_id == service_account_id,
            )
        )
        if result.one_or_none() is None:
            trigger = await self.session.get(WebhookTrigger, trigger_id)
            raise WebhookServiceAccountNotAuthorizedError(
                webhook_path=trigger.webhook_path if trigger else _UNKNOWN,
                trigger_type=trigger.trigger_type if trigger else _UNKNOWN,
                service_account_id=service_account_id,
            )

    async def get_by_webhook_path(
        self,
        webhook_path: str,
        trigger_type: str = NodeType.WEBHOOK_TRIGGER,
    ) -> WebhookTrigger:
        """Look up a webhook trigger by its path and type.

        Args:
            webhook_path: The URL slug to look up.
            trigger_type: The trigger type to filter by (default: "webhook_trigger").

        Returns:
            The matching WebhookTrigger record.

        Raises:
            WebhookTriggerNotFoundError: If no trigger exists for this path/type.

        """
        result = await self.session.exec(
            select(WebhookTrigger)
            .join(Workflow, WebhookTrigger.workflow_id == Workflow.id)  # type: ignore[arg-type]
            .where(
                WebhookTrigger.trigger_type == trigger_type,
                WebhookTrigger.webhook_path == webhook_path,
                WebhookTrigger.is_enabled == True,  # noqa: E712
                Workflow.is_enabled == True,  # noqa: E712
                Workflow.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        trigger = result.one_or_none()
        if trigger is None:
            raise WebhookTriggerNotFoundError(webhook_path, trigger_type=trigger_type)
        return trigger

    async def sync_webhook_triggers(
        self,
        workflow_id: UUID,
        workflow_definition: dict[str, Any],
        *,
        is_enabled: bool = True,
        trigger_type: str = NodeType.WEBHOOK_TRIGGER,
    ) -> list[WebhookTriggerRead]:
        """Synchronise webhook trigger lookup rows from a workflow definition.

        Compares trigger nodes in the definition against existing DB rows
        for the given ``trigger_type``. Creates new rows, updates existing
        ones, and deletes removed ones.

        Args:
            workflow_id: The workflow ID.
            workflow_definition: The full workflow definition dict.
            is_enabled: Whether the workflow is enabled.
            trigger_type: The trigger type to sync (default: "webhook_trigger").

        Returns:
            List of WebhookTriggerRead for synced triggers.

        Raises:
            TriggerValidationError: If a webhook trigger node has an
                invalid or missing webhook_path.
            WebhookTriggerPathConflictError: If a webhook path is already used
                by a different workflow.

        """
        webhook_nodes = self._extract_webhook_nodes(workflow_definition, trigger_type, workflow_id)

        result = await self.session.exec(
            select(WebhookTrigger).where(
                WebhookTrigger.workflow_id == workflow_id,
                WebhookTrigger.trigger_type == trigger_type,
            )
        )
        existing_triggers = {t.trigger_node_id: t for t in result.all()}

        results, sa_bindings = self._upsert_triggers(
            webhook_nodes, existing_triggers, workflow_id, trigger_type, is_enabled=is_enabled
        )

        for trigger in existing_triggers.values():
            await self.session.delete(trigger)
            logger.info(
                "Deleted webhook trigger for removed node",
                trigger_id=trigger.id,
                trigger_node_id=trigger.trigger_node_id,
                webhook_path=trigger.webhook_path,
            )

        await self._flush_with_conflict_guard()

        for trigger_id, desired_sa_ids in sa_bindings:
            await self._sync_trigger_sa_bindings(trigger_id, desired_sa_ids, workflow_id)

        logger.info(
            "Synced webhook triggers",
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            total=len(results),
            deleted=len(existing_triggers),
        )

        return results

    @staticmethod
    def _extract_webhook_nodes(
        workflow_definition: dict[str, Any], trigger_type: str, workflow_id: UUID
    ) -> dict[str, dict[str, Any]]:
        """Extract trigger nodes matching the given type from a workflow definition."""
        webhook_nodes: dict[str, dict[str, Any]] = {}
        for trigger in workflow_definition.get("triggers", []):
            if trigger.get("type") != trigger_type:
                continue
            node_id = trigger.get("id")
            if not node_id:
                logger.warning(
                    "Skipping trigger with missing id",
                    workflow_id=str(workflow_id),
                    trigger_type=trigger_type,
                )
                continue
            webhook_nodes[node_id] = trigger.get("parameters", {})
        return webhook_nodes

    def _upsert_triggers(
        self,
        webhook_nodes: dict[str, dict[str, Any]],
        existing_triggers: dict[str, WebhookTrigger],
        workflow_id: UUID,
        trigger_type: str,
        *,
        is_enabled: bool,
    ) -> tuple[list[WebhookTriggerRead], list[tuple[UUID, set[UUID]]]]:
        """Create or update triggers, returning results and SA bindings to sync."""
        results: list[WebhookTriggerRead] = []
        sa_bindings: list[tuple[UUID, set[UUID]]] = []

        for node_id, parameters in webhook_nodes.items():
            try:
                validated = WebhookTriggerParameters.model_validate(parameters)
            except ValidationError as e:
                msg = f"Invalid webhook trigger parameters for node '{node_id}': {e}"
                raise TriggerValidationError(msg) from e

            if node_id in existing_triggers:
                trigger = existing_triggers.pop(node_id)
                trigger.webhook_path = validated.webhook_path
                trigger.input_schema = validated.input_schema
                trigger.is_enabled = is_enabled
            else:
                trigger = WebhookTrigger(
                    id=uuid4(),
                    trigger_type=trigger_type,
                    webhook_path=validated.webhook_path,
                    workflow_id=workflow_id,
                    trigger_node_id=node_id,
                    input_schema=validated.input_schema,
                    is_enabled=is_enabled,
                )

            self.session.add(trigger)
            results.append(WebhookTriggerRead.model_validate(trigger))
            sa_bindings.append((trigger.id, set(validated.authorized_service_account_ids)))

        return results, sa_bindings

    async def _flush_with_conflict_guard(self) -> None:
        """Flush the session, converting path uniqueness violations to domain errors."""
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            error_str = str(e)
            if "ix_webhook_triggers_type_path_unique" in error_str or "webhook_path" in error_str:
                match = re.search(r"Key \(trigger_type, webhook_path\)=\([^,]+, ([^)]+)\)", error_str)
                conflicting_path = match.group(1) if match else _UNKNOWN
                raise WebhookTriggerPathConflictError(conflicting_path) from e
            raise

    async def _sync_trigger_sa_bindings(
        self,
        trigger_id: UUID,
        desired_sa_ids: set[UUID],
        workflow_id: UUID,
    ) -> None:
        """Sync the authorized service account bindings for a trigger."""
        if desired_sa_ids:
            workflow = await self.session.get(Workflow, workflow_id)
            project_id = workflow.project_id if workflow else None
            query = select(ServiceAccount.id).where(col(ServiceAccount.id).in_(desired_sa_ids))
            if project_id:
                query = query.where(ServiceAccount.project_id == project_id)
            result = await self.session.exec(query)
            found_ids = set(result.all())
            missing = desired_sa_ids - found_ids
            if missing:
                msg = f"Service account(s) not found in this project: {', '.join(str(i) for i in missing)}"
                raise TriggerValidationError(msg)

        existing_result = await self.session.exec(
            select(WebhookTriggerServiceAccount).where(
                WebhookTriggerServiceAccount.webhook_trigger_id == trigger_id,
            )
        )
        existing_sa_ids = {link.service_account_id for link in existing_result.all()}

        to_remove = existing_sa_ids - desired_sa_ids
        for sa_id_to_remove in to_remove:
            stmt = sa_delete(WebhookTriggerServiceAccount).where(
                WebhookTriggerServiceAccount.webhook_trigger_id == trigger_id,  # type: ignore[arg-type]
                WebhookTriggerServiceAccount.service_account_id == sa_id_to_remove,  # type: ignore[arg-type]
            )
            await self.session.execute(stmt)

        for sa_id in desired_sa_ids - existing_sa_ids:
            self.session.add(
                WebhookTriggerServiceAccount(
                    webhook_trigger_id=trigger_id,
                    service_account_id=sa_id,
                )
            )

    async def delete_triggers_for_workflow(self, workflow_id: UUID) -> int:
        """Delete all webhook triggers for a workflow.

        Args:
            workflow_id: The workflow ID.

        Returns:
            Number of triggers deleted.

        """
        result = await self.session.exec(select(WebhookTrigger).where(WebhookTrigger.workflow_id == workflow_id))
        triggers = result.all()
        for trigger in triggers:
            await self.session.delete(trigger)

        if triggers:
            await self.session.flush()
            logger.info(
                "Deleted webhook triggers for workflow",
                workflow_id=workflow_id,
                count=len(triggers),
            )

        return len(triggers)
