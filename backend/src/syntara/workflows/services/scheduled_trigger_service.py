"""Service for managing scheduled trigger Temporal Schedules.

Scheduled triggers are managed entirely through Temporal Schedules. No database
model is needed because the schedule ID is deterministic:
``orchestrator-sched-{workflow_id}-{trigger_node_id}``.

This service synchronises Temporal Schedules when workflows are created,
updated, published, unpublished, or deleted.
"""

import asyncio
from typing import Any

import structlog
from pydantic import ValidationError
from temporalio.api.enums.v1 import IndexedValueType
from temporalio.api.operatorservice.v1 import (
    AddSearchAttributesRequest,
    ListSearchAttributesRequest,
)
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleState,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.common import SearchAttributeKey, SearchAttributePair, TypedSearchAttributes
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.config.base import get_settings
from syntara.core.tls.temporal import build_temporal_tls_config
from syntara.workflows.exceptions import ScheduledTriggerSyncError, TriggerValidationError
from syntara.workflows.utils.schedule_parser import (
    SCHEDULE_ID_PREFIX,
    build_schedule_execution_workflow_id,
    build_schedule_id,
    config_to_temporal_schedule,
)
from syntara.workflows.validators import collect_scheduled_trigger_config_findings
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, ScheduledTriggerConfig
from syntara.workflows.workflow_engine.workflow_auth import build_auth_header

logger = structlog.stdlib.get_logger(__name__)

SA_ORCHESTRATOR_WORKFLOW_ID = SearchAttributeKey.for_keyword("OrchestratorWorkflowId")

_client_lock = asyncio.Lock()
_cached_client: Client | None = None

_search_attr_available: bool | None = None

_CONNECTION_ERRORS = frozenset({RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED})


async def _update_schedule_with_retry(
    client: Client,
    schedule_id: str,
    schedule: Schedule,
    search_attributes: TypedSearchAttributes | None = None,
) -> None:
    """Update an existing Temporal Schedule, retrying if the action is in-flight."""
    handle = client.get_schedule_handle(schedule_id)

    def _updater(_: ScheduleUpdateInput) -> ScheduleUpdate:
        return ScheduleUpdate(schedule=schedule, search_attributes=search_attributes)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await handle.update(_updater)
            return
        except ScheduleAlreadyRunningError:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2)


def _invalidate_client_cache() -> None:
    """Clear the cached Temporal client so the next call reconnects."""
    global _cached_client, _search_attr_available  # noqa: PLW0603
    _cached_client = None
    _search_attr_available = None


async def _ensure_search_attribute(client: Client) -> bool:
    """Ensure the OrchestratorWorkflowId search attribute is registered in Temporal.

    Returns True if the attribute is available for server-side filtering,
    False if the Temporal server does not support it.  The result is cached
    for the lifetime of the client connection.
    """
    global _search_attr_available  # noqa: PLW0603

    if _search_attr_available is not None:
        return _search_attr_available

    try:
        settings = get_settings()
        resp = await client.operator_service.list_search_attributes(
            ListSearchAttributesRequest(namespace=settings.temporal_namespace),
        )
        attr_type = resp.custom_attributes.get(SA_ORCHESTRATOR_WORKFLOW_ID.name)
        if attr_type == IndexedValueType.INDEXED_VALUE_TYPE_KEYWORD:
            _search_attr_available = True
            logger.info("OrchestratorWorkflowId search attribute already registered")
            return True
        if attr_type is not None:
            logger.warning(
                "OrchestratorWorkflowId has unexpected type, using prefix scan fallback",
                type=attr_type,
            )
            _search_attr_available = False
            return False

        try:
            await client.operator_service.add_search_attributes(
                AddSearchAttributesRequest(
                    namespace=settings.temporal_namespace,
                    search_attributes={
                        SA_ORCHESTRATOR_WORKFLOW_ID.name: IndexedValueType.INDEXED_VALUE_TYPE_KEYWORD,
                    },
                ),
            )
        except RPCError as add_err:
            if add_err.status != RPCStatusCode.ALREADY_EXISTS:
                raise
            logger.info("OrchestratorWorkflowId registered concurrently by another replica")
        else:
            logger.info("Registered OrchestratorWorkflowId search attribute")
        _search_attr_available = True
        return True

    except RPCError as e:
        _search_attr_available = False
        logger.info(
            "Custom search attributes not available, using prefix scan fallback",
            error=str(e),
            status=e.status.name,
        )
        return False


async def _get_shared_client() -> Client | None:
    """Return a module-level cached Temporal client.

    Connects once and reuses across all ``ScheduledTriggerService`` instances
    so that lifecycle hooks share a single gRPC connection.  The cache is
    invalidated on connection-level errors so the next call reconnects.
    """
    global _cached_client  # noqa: PLW0603
    async with _client_lock:
        if _cached_client is not None:
            return _cached_client

        try:
            settings = get_settings()
            _cached_client = await Client.connect(
                settings.temporal_address,
                namespace=settings.temporal_namespace,
                tls=build_temporal_tls_config(),
            )
            return _cached_client
        except (OSError, RuntimeError, RPCError) as e:
            logger.warning("Temporal unavailable for schedule management", error=str(e))
            return None


class ScheduledTriggerService:
    """Service for managing Temporal Schedules for scheduled triggers.

    Unlike WebhookTriggerService which maintains a database lookup table,
    this service manages Temporal Schedules directly using deterministic
    schedule IDs derived from ``workflow_id`` and ``trigger_node_id``.

    Does not inherit from BaseService because it manages Temporal
    Schedules (external system) rather than database records.  No session
    or user context is required.
    """

    def __init__(self, temporal_client: Client | None = None) -> None:
        """Initialize ScheduledTriggerService.

        Args:
            temporal_client: Optional Temporal client for testing. If None,
                the shared module-level connection is used.

        """
        self._temporal_client = temporal_client

    async def get_client(self) -> Client | None:
        """Get a Temporal client.

        Uses the injected client if provided, otherwise the shared connection.
        """
        if self._temporal_client is not None:
            return self._temporal_client
        return await _get_shared_client()

    @staticmethod
    def validate_trigger_configs(workflow_definition: dict[str, Any]) -> None:
        """Pre-validate all scheduled trigger configs without contacting Temporal.

        Raise-first wrapper around
        ``collect_scheduled_trigger_config_findings`` so Temporal sync and
        ``WorkflowValidator.collect_findings`` share one walk / one id and
        config-handling policy. Used by ``sync_scheduled_triggers`` as a
        defense-in-depth guard after publish's pre-mutation
        ``collect_findings`` check.

        Raises:
            TriggerValidationError: If any scheduled trigger config is invalid.

        """
        findings = collect_scheduled_trigger_config_findings(workflow_definition)
        if findings:
            raise TriggerValidationError(findings[0].message)

    async def sync_scheduled_triggers(
        self,
        workflow_id: str,
        workflow_definition: dict[str, Any],
        *,
        is_builtin: bool = False,
    ) -> int:
        """Synchronise Temporal Schedules from a workflow definition.

        Creates or updates schedules for each scheduled trigger node and
        deletes schedules for trigger nodes that were removed.  Only called
        on publish.  Unpublish and delete use
        ``WorkflowService._delete_scheduled_triggers`` for best-effort
        cleanup; the schedule reconciliation worker handles any orphans.

        Args:
            workflow_id: The workflow UUID (as string).
            workflow_definition: The full workflow definition dict.
            is_builtin: When True, routes to ``settings.background_task_queue``
                instead of ``settings.task_queue`` — same branch
                ``TemporalExecutionService`` uses for manually-triggered
                builtin executions.

        Returns:
            Number of scheduled triggers processed.

        Raises:
            TriggerValidationError: If a scheduled trigger config is invalid.

        """
        self.validate_trigger_configs(workflow_definition)

        # Extract scheduled trigger nodes from definition
        triggers = workflow_definition.get("triggers", [])
        scheduled_nodes: dict[str, dict[str, Any]] = {}
        for trigger in triggers:
            if trigger.get("type") == NodeType.SCHEDULED_TRIGGER:
                node_id = trigger.get("id")
                if not node_id:
                    logger.warning(
                        "Skipping scheduled trigger with missing id",
                        workflow_id=workflow_id,
                    )
                    continue
                scheduled_nodes[node_id] = trigger.get("parameters", {})

        client = await self.get_client()
        if client is None:
            if scheduled_nodes:
                raise ScheduledTriggerSyncError(workflow_id, len(scheduled_nodes))
            return 0

        settings = get_settings()
        task_queue = settings.background_task_queue if is_builtin else settings.task_queue
        processed = 0

        try:
            # Create or update schedules for current trigger nodes.
            # Configs are already validated by validate_trigger_configs() above.
            for node_id, config in scheduled_nodes.items():
                schedule_id = build_schedule_id(workflow_id, node_id)
                await self._create_or_update_schedule(client, schedule_id, workflow_id, node_id, config, task_queue)
                processed += 1

            # Delete schedules for trigger nodes removed from the definition
            expected_ids = {build_schedule_id(workflow_id, nid) for nid in scheduled_nodes}
            existing_ids = await self._list_workflow_schedules(client, workflow_id)
            stale_ids = existing_ids - expected_ids
            for stale_id in stale_ids:
                await self.delete_schedule(client, stale_id)
                logger.info(
                    "Deleted stale Temporal Schedule for removed trigger node",
                    schedule_id=stale_id,
                    workflow_id=workflow_id,
                )
        except (OSError, RuntimeError, RPCError) as exc:
            raise ScheduledTriggerSyncError(workflow_id, len(scheduled_nodes)) from exc

        logger.info(
            "Synced scheduled triggers",
            workflow_id=workflow_id,
            total=processed,
        )

        return processed

    async def delete_triggers_for_workflow(
        self,
        workflow_id: str,
    ) -> int:
        """Delete all Temporal Schedules for a workflow.

        Finds schedules via the OrchestratorWorkflowId search attribute when
        available, falling back to prefix scan otherwise.  Does not
        iterate the workflow definition, so schedules created by any
        version are cleaned up — not just those in the current draft.

        Args:
            workflow_id: The workflow UUID (as string).

        Returns:
            Number of schedules deleted.

        """
        client = await self.get_client()
        if client is None:
            logger.warning(
                "Skipping schedule deletion: Temporal unavailable",
                workflow_id=workflow_id,
            )
            return 0

        try:
            all_schedule_ids = await self._list_workflow_schedules(client, workflow_id)
            deleted = 0

            for schedule_id in all_schedule_ids:
                if await self.delete_schedule(client, schedule_id):
                    deleted += 1
        except (OSError, RuntimeError, RPCError) as exc:
            raise ScheduledTriggerSyncError(workflow_id, 0) from exc

        if deleted:
            logger.info(
                "Deleted scheduled triggers for workflow",
                workflow_id=workflow_id,
                count=deleted,
            )

        return deleted

    async def create_schedule(
        self,
        workflow_id: str,
        trigger_node_id: str,
        config: dict[str, Any],
    ) -> str:
        """Create or update a single Temporal Schedule for a trigger node.

        Validates the trigger config and delegates to the low-level
        create-or-update helper.  Intended for reconciliation — when a
        schedule is known to be missing and needs to be (re-)created
        without running a full ``sync_scheduled_triggers`` cycle.

        Args:
            workflow_id: The workflow UUID (as string).
            trigger_node_id: The trigger node ID within the workflow definition.
            config: The scheduled trigger parameters dict.

        Returns:
            The deterministic schedule ID.

        Raises:
            TriggerValidationError: If the trigger config is invalid.
            RuntimeError: If the Temporal client is unavailable.

        """
        client = await self.get_client()
        if client is None:
            msg = "Temporal client unavailable"
            raise RuntimeError(msg)

        try:
            ScheduledTriggerConfig.model_validate(config)
        except ValidationError as e:
            msg = f"Invalid scheduled trigger config for node '{trigger_node_id}': {e}"
            raise TriggerValidationError(msg) from e

        settings = get_settings()
        schedule_id = build_schedule_id(workflow_id, trigger_node_id)
        await self._create_or_update_schedule(
            client, schedule_id, workflow_id, trigger_node_id, config, settings.task_queue
        )
        return schedule_id

    async def _create_or_update_schedule(
        self,
        client: Client,
        schedule_id: str,
        workflow_id: str,
        trigger_node_id: str,
        config: dict[str, Any],
        task_queue: str,
    ) -> None:
        """Create or update a Temporal Schedule.

        If the schedule already exists, it is updated. Otherwise, a new
        schedule is created.
        """
        spec, policy = config_to_temporal_schedule(config)

        schedule_workflow_id = build_schedule_execution_workflow_id(workflow_id, trigger_node_id)
        action = ScheduleActionStartWorkflow(
            "scheduled_workflow_launcher",
            args=[workflow_id, trigger_node_id],
            id=schedule_workflow_id,
            task_queue=task_queue,
        )
        action.headers = build_auth_header(
            schedule_workflow_id, "scheduled_workflow_launcher", [workflow_id, trigger_node_id]
        )

        schedule = Schedule(
            action=action,
            spec=spec,
            policy=policy,
            state=ScheduleState(paused=False),
        )

        search_attrs: TypedSearchAttributes | None = None
        if await _ensure_search_attribute(client):
            search_attrs = TypedSearchAttributes(
                [SearchAttributePair(SA_ORCHESTRATOR_WORKFLOW_ID, workflow_id)],
            )

        try:
            await client.create_schedule(schedule_id, schedule, search_attributes=search_attrs)
            logger.info(
                "Created Temporal Schedule",
                schedule_id=schedule_id,
                workflow_id=workflow_id,
                trigger_node_id=trigger_node_id,
            )
        except (RPCError, ScheduleAlreadyRunningError) as e:
            if isinstance(e, ScheduleAlreadyRunningError) or (
                isinstance(e, RPCError) and e.status == RPCStatusCode.ALREADY_EXISTS
            ):
                await _update_schedule_with_retry(client, schedule_id, schedule, search_attrs)
                logger.info(
                    "Updated Temporal Schedule",
                    schedule_id=schedule_id,
                    workflow_id=workflow_id,
                    trigger_node_id=trigger_node_id,
                )
            elif isinstance(e, RPCError) and e.status in _CONNECTION_ERRORS:
                _invalidate_client_cache()
                raise
            else:
                raise

    async def _list_workflow_schedules(self, client: Client, workflow_id: str) -> set[str]:
        """List all Temporal Schedule IDs belonging to a workflow.

        Uses the OrchestratorWorkflowId search attribute for server-side
        filtering when available, falling back to prefix scan otherwise.
        """
        can_use_search_attr = await _ensure_search_attribute(client) and workflow_id.replace("-", "").isalnum()
        if can_use_search_attr:
            result = await self._list_schedules_by_query(
                client, f'{SA_ORCHESTRATOR_WORKFLOW_ID.name} = "{workflow_id}"'
            )
            if result is not None:
                return result

        return await self.list_schedules_by_prefix(client, workflow_id)

    async def list_all_schedules(self, client: Client) -> set[str]:
        """List all orchestrator-managed Temporal Schedule IDs.

        Uses the OrchestratorWorkflowId search attribute for server-side
        filtering when available, falling back to prefix scan otherwise.
        """
        if await _ensure_search_attribute(client):
            result = await self._list_schedules_by_query(client, f'{SA_ORCHESTRATOR_WORKFLOW_ID.name} != ""')
            if result is not None:
                return result

        return await self.list_schedules_by_prefix(client)

    async def _list_schedules_by_query(self, client: Client, query: str) -> set[str] | None:
        """Run a server-side schedule query, returning None on non-connection errors."""
        try:
            schedule_ids: set[str] = set()
            async for entry in await client.list_schedules(query=query):
                schedule_ids.add(entry.id)
            return schedule_ids
        except RPCError as e:
            if e.status in _CONNECTION_ERRORS:
                _invalidate_client_cache()
                raise
            logger.warning(
                "Search attribute query failed, falling back to prefix scan",
                query=query,
                error=str(e),
            )
            return None

    @staticmethod
    async def list_schedules_by_prefix(client: Client, prefix: str = "") -> set[str]:
        """List orchestrator-managed Temporal Schedule IDs, optionally narrowed by *prefix*."""
        match_prefix = f"{SCHEDULE_ID_PREFIX}{prefix}-" if prefix else SCHEDULE_ID_PREFIX
        schedule_ids: set[str] = set()
        async for entry in await client.list_schedules():
            if entry.id.startswith(match_prefix):
                schedule_ids.add(entry.id)
        return schedule_ids

    @staticmethod
    async def delete_schedule(client: Client, schedule_id: str) -> bool:
        """Delete a Temporal Schedule if it exists.

        Returns True if a schedule was deleted, False if it didn't exist.
        """
        handle = client.get_schedule_handle(schedule_id)
        try:
            await handle.delete()
            logger.info("Deleted Temporal Schedule", schedule_id=schedule_id)
            return True
        except RPCError as e:
            if e.status != RPCStatusCode.NOT_FOUND:
                if e.status in _CONNECTION_ERRORS:
                    _invalidate_client_cache()
                raise
            logger.debug("No schedule to delete", schedule_id=schedule_id)
            return False
