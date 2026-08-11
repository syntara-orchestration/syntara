"""Seed built-in workflow definitions.

Definitions are embedded as Python constants so they are always available,
even in container images that only sync ``*.py`` files (e.g. Skaffold).

Registered as a **required** seeder — always runs during seeding.
Built-in workflows cannot be deleted or modified by users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
from sqlmodel import col, select

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.workflows.constants import BUILTIN_PROJECT_NAME
from syntara.workflows.exceptions import ScheduledTriggerSyncError
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.services.scheduled_trigger_service import ScheduledTriggerService
from syntara.workflows.validators import workflow_validator

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

_BUILTIN_DEFINITIONS: list[dict[str, Any]] = [
    {
        "schema_version": "2.0.0",
        "name": "Document Conversion",
        "description": (
            "System workflow that converts uploaded documents to markdown format. "
            "Triggered automatically when files are uploaded."
        ),
        "triggers": [{"id": "trigger_api", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "convert",
                "type": "internal_activity",
                "name": "Convert Document",
                "parameters": {
                    "activity": "document_conversion",
                    "input": {"file_id": "${trigger.file_id}"},
                },
                "settings": {
                    "retry_policy": {
                        "max_retries": 2,
                        "initial_interval": 5,
                        "backoff_coefficient": 2.0,
                    },
                    "timeout": 300,
                },
            }
        ],
        "edges": [{"from": "trigger_api", "to": "convert"}],
    },
    {
        "schema_version": "2.0.0",
        "name": "Agent Execution",
        "description": (
            "System workflow that executes agent invocations. Triggered automatically when an invocation is created."
        ),
        "triggers": [{"id": "trigger_api", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "execute",
                "type": "internal_activity",
                "name": "Execute Invocation",
                "parameters": {
                    "activity": "invocation_execution",
                    "input": {"invocation_id": "${trigger.invocation_id}"},
                },
                "settings": {"timeout": 3600},
            }
        ],
        "edges": [{"from": "trigger_api", "to": "execute"}],
    },
    {
        "schema_version": "2.0.0",
        "name": "Integration Health Check",
        "description": (
            "Scheduled workflow that validates integrations on a recurring interval. "
            "Checks all integrations due for validation based on health_check_interval_seconds."
        ),
        "triggers": [
            {
                "id": "trigger_schedule",
                "type": "scheduled_trigger",
                "parameters": {
                    "schedule_type": "interval",
                    "interval": "R/2024-01-01T00:00:00Z/PT5M",
                    "missed_schedule_policy": "skip",
                },
            }
        ],
        "nodes": [
            {
                "id": "health_check",
                "type": "internal_activity",
                "name": "Run Integration Health Checks",
                "parameters": {
                    "activity": "integration_health_check",
                    # Batch mode: check all stale integrations
                    "input": {"batch": True},
                },
                "settings": {
                    # No retries: next scheduled tick serves as implicit retry.
                    "timeout": 280,
                    "retry_policy": {
                        "max_retries": 0,
                    },
                },
            }
        ],
        "edges": [{"from": "trigger_schedule", "to": "health_check"}],
    },
    {
        "schema_version": "2.0.0",
        "name": "Integration Resource Discovery",
        "description": (
            "Scheduled workflow that re-discovers and syncs integration resources "
            "(MCP tools, LLM models) on a recurring interval. Refreshes integrations "
            "due based on discovery_interval_seconds."
        ),
        "triggers": [
            {
                "id": "trigger_schedule",
                "type": "scheduled_trigger",
                "parameters": {
                    "schedule_type": "interval",
                    "interval": "R/2024-01-01T00:00:00Z/PT30M",
                    "missed_schedule_policy": "skip",
                },
            }
        ],
        "nodes": [
            {
                "id": "resource_discovery",
                "type": "internal_activity",
                "name": "Run Integration Resource Discovery",
                "parameters": {
                    "activity": "integration_resource_discovery",
                    # Batch mode: discover all due integrations
                    "input": {"batch": True},
                },
                "settings": {
                    # No retries (next tick is the implicit retry). Timeout stays well
                    # under the 30-minute interval so a slow pass can't overlap the next.
                    "timeout": 600,
                    "retry_policy": {
                        "max_retries": 0,
                    },
                },
            }
        ],
        "edges": [{"from": "trigger_schedule", "to": "resource_discovery"}],
    },
]


async def seed_builtin_workflows(session: AsyncSession) -> None:
    """Load builtin workflows into the database.

    Idempotent: if a builtin workflow already exists, its definition is
    compared and updated only if changed (new version created).

    Args:
        session: Database session (caller manages lifecycle).

    """
    result = await session.exec(
        select(User).where(
            User.username == "admin",
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    user = result.first()
    if not user:
        msg = "No admin user found — cannot seed builtin workflows. Ensure authz seeder runs first."
        raise RuntimeError(msg)

    project_result = await session.exec(
        select(Project).where(
            Project.name == BUILTIN_PROJECT_NAME,
            Project.is_builtin == True,  # noqa: E712
            Project.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    system_project = project_result.first()
    if not system_project:
        msg = "Built-in project not found — cannot seed builtin workflows. Ensure authz seeder runs first."
        raise RuntimeError(msg)
    project_id = system_project.id

    for workflow_dict in _BUILTIN_DEFINITIONS:
        try:
            await _seed_one(session, workflow_dict, user.id, project_id)
        except Exception:
            logger.exception("Failed to seed builtin workflow", workflow_name=workflow_dict.get("name"))
            continue

    await session.commit()
    logger.info("Builtin workflow seeding complete")


async def _sync_builtin_schedules(workflow_id: UUID, workflow_dict: dict[str, Any], name: str) -> None:
    """Create/update Temporal Schedules for scheduled_trigger nodes in a builtin workflow.

    Builtin workflows are seeded directly, bypassing WorkflowService's normal
    publish flow — so they'd never get a real Temporal Schedule without this.
    Called on every seed pass (not just first creation) so a pod restart
    re-syncs idempotently; sync_scheduled_triggers() is a no-op on repeat
    calls with an unchanged definition.
    """
    try:
        scheduled_service = ScheduledTriggerService()
        count = await scheduled_service.sync_scheduled_triggers(
            workflow_id=str(workflow_id),
            workflow_definition=workflow_dict,
            is_builtin=True,
        )
        if count:
            logger.info(
                "Synced scheduled triggers for builtin workflow",
                workflow_name=name,
                trigger_count=count,
            )
    except ScheduledTriggerSyncError as exc:
        # Non-fatal: the workflow row itself is still seeded correctly even
        # if Temporal is unreachable at startup. Mirrors the same
        # degrade-gracefully behaviour WorkflowService uses on publish.
        logger.warning(
            "Scheduled trigger sync failed for builtin workflow — schedule not created/updated",
            workflow_name=name,
            error=str(exc),
        )


async def _seed_one(
    session: AsyncSession,
    workflow_dict: dict[str, Any],
    creator_id: UUID,
    project_id: UUID,
) -> None:
    name = workflow_dict["name"]

    workflow_validator.validate_workflow_definition(workflow_dict)

    result = await session.exec(
        select(Workflow).where(
            col(Workflow.name) == name,
            col(Workflow.is_builtin) == True,  # noqa: E712
            Workflow.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    existing = result.one_or_none()

    if existing is None:
        workflow = Workflow(
            id=uuid4(),
            name=name,
            description=workflow_dict.get("description", ""),
            labels={"built-in": ""},
            current_version=1,
            is_builtin=True,
            is_enabled=False,
            created_by=creator_id,
            project_id=project_id,
        )
        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version=workflow_dict.get("schema_version", "2.0.0"),
            workflow_definition=workflow_dict,
            created_by=creator_id,
            change_description="Initial builtin workflow",
        )
        session.add(workflow)
        session.add(version)
        await session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True
        publish_event = WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=creator_id,
        )
        session.add(publish_event)
        logger.info("Created builtin workflow", workflow_name=name)
        await _sync_builtin_schedules(workflow.id, workflow_dict, name)
    else:
        current_version_result = await session.exec(
            select(WorkflowVersion).where(
                col(WorkflowVersion.workflow_id) == existing.id,
                col(WorkflowVersion.version) == existing.current_version,
            )
        )
        current_version = current_version_result.one_or_none()

        if existing.project_id != project_id:
            existing.project_id = project_id
            logger.info("Updated builtin workflow project", workflow_name=name)

        if current_version and current_version.workflow_definition == workflow_dict:
            logger.info("Builtin workflow unchanged, skipping", workflow_name=name)
            # Still re-sync schedules even when unchanged (see docstring).
            await _sync_builtin_schedules(existing.id, workflow_dict, name)
            return

        new_version_num = existing.increment_version()

        new_version = WorkflowVersion(
            id=uuid4(),
            workflow_id=existing.id,
            version=new_version_num,
            schema_version=workflow_dict.get("schema_version", "2.0.0"),
            workflow_definition=workflow_dict,
            created_by=creator_id,
            change_description="Updated builtin workflow definition",
        )
        existing.description = workflow_dict.get("description", "")
        session.add(new_version)
        await session.flush()
        existing.published_version_id = new_version.id
        publish_event = WorkflowPublishEvent(
            workflow_id=existing.id,
            version_id=new_version.id,
            action=PublishAction.PUBLISHED,
            actor_id=creator_id,
        )
        session.add(publish_event)
        logger.info("Updated builtin workflow", workflow_name=name, new_version=new_version_num)
        await _sync_builtin_schedules(existing.id, workflow_dict, name)
