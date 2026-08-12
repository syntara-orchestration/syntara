"""Temporal activity for validating integration, model, and tool references at execution time.

Re-checks that all referenced resources are accessible, enabled, and of the
correct type before dispatching a node to its executor. Guards fire even if
resources were valid when the workflow was saved.
"""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.exc import OperationalError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.database.session import AsyncSessionLocal
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.llm_model import LLMModel
from syntara.tool_manager.models.tool import Tool
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType

logger = structlog.stdlib.get_logger(__name__)

_session_factory = AsyncSessionLocal

_AAP_NODE_TYPES: frozenset[str] = frozenset({NodeType.AAP_JOB_TEMPLATE, NodeType.AAP_WORKFLOW_JOB_TEMPLATE})


def _is_valid_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


@activity.defn(name=ActivityName.VALIDATE_NODE_REFERENCES)
async def validate_node_references(
    node_type: str,
    node_id: str,
    reference_ids: dict[str, Any],
    project_id: str,
) -> None:
    """Validate that all integration/model/tool references in a node are accessible.

    Args:
        node_type: The node's type (e.g. "aap_job_template", "agentic").
        node_id: The node's ID (for logging).
        reference_ids: Pre-extracted reference fields from node parameters.
        project_id: The workflow's project UUID string.

    Raises:
        ApplicationError: Non-retryable error if any reference is invalid.
            Possible error types: IntegrationNotFoundError, IntegrationNotAccessibleError,
            IntegrationDisabledError, IntegrationTypeMismatchError, LLMModelNotFoundError,
            LLMModelDisabledError, ToolsUnavailableError.

    """
    try:
        async with _session_factory() as session:
            await _validate_node(session, node_type, node_id, reference_ids, project_id)
    except ApplicationError:
        raise
    except OperationalError as e:
        msg = f"Transient database error during reference validation: {type(e).__name__}"
        raise ApplicationError(msg, non_retryable=False) from e
    except Exception as e:
        msg = f"Database error during reference validation: {type(e).__name__}"
        raise ApplicationError(msg, non_retryable=True) from e


async def _extract_tool_parent_ids(session: AsyncSession, tool_selections: list[str]) -> set[UUID]:
    """Look up the parent integration IDs for the given tool selections."""
    valid_ids = [UUID(tid) for tid in tool_selections if _is_valid_uuid(tid)]
    if not valid_ids:
        return set()
    result = await session.execute(select(Tool.integration_id).where(col(Tool.id).in_(valid_ids)).distinct())
    return {iid for iid in result.scalars().all() if iid is not None}


async def _validate_node(
    session: AsyncSession,
    node_type: str,
    node_id: str,
    reference_ids: dict[str, Any],
    project_id: str,
) -> None:
    integration_ids: set[UUID] = set()
    expected_types: dict[UUID, str] = {}

    if node_type in _AAP_NODE_TYPES:
        direct_id = reference_ids.get("integration_id")
        if direct_id and _is_valid_uuid(direct_id):
            parsed = UUID(direct_id)
            integration_ids.add(parsed)
            expected_types[parsed] = IntegrationType.ANSIBLE_AUTOMATION_PLATFORM

    if node_type == NodeType.AGENTIC:
        for conn in reference_ids.get("integration_connections") or []:
            conn_id = conn.get("integration_id")
            if conn_id and _is_valid_uuid(conn_id):
                parsed = UUID(conn_id)
                integration_ids.add(parsed)
                expected_types[parsed] = IntegrationType.MCP_SERVER

    llm_model_id = reference_ids.get("llm_model_id")
    if llm_model_id and _is_valid_uuid(llm_model_id):
        model_integration_ids = await _validate_llm_model(session, llm_model_id)
        integration_ids |= model_integration_ids

    tool_strategy = reference_ids.get("tool_selection_strategy")
    tool_selections = reference_ids.get("tool_selections")
    if tool_strategy == "SELECTED" and tool_selections:
        integration_ids |= await _extract_tool_parent_ids(session, tool_selections)

    if integration_ids:
        await _validate_integrations(session, integration_ids, expected_types, project_id, node_id)

    if tool_strategy == "SELECTED" and tool_selections:
        await _validate_tools(session, tool_selections)

    logger.info(
        "Node references validated",
        node_type=node_type,
        node_id=node_id,
        integration_count=len(integration_ids),
        tool_count=len(tool_selections or []),
        llm_model_validated=bool(llm_model_id and _is_valid_uuid(llm_model_id)),
    )


async def _validate_llm_model(session: AsyncSession, model_id_str: str) -> set[UUID]:
    """Check LLM model exists and is enabled.

    Returns:
        set[UUID]: Integration IDs associated with the validated model, passed to
        _validate_integrations for scope/enabled/type checks on the parent provider.

    Raises:
        ApplicationError (LLMModelNotFoundError): Model UUID not found in the database.
        ApplicationError (LLMModelDisabledError): Model exists but is disabled.

    """
    parsed = UUID(model_id_str)
    result = await session.execute(
        select(LLMModel.id, LLMModel.integration_id, LLMModel.enabled, LLMModel.name).where(LLMModel.id == parsed)
    )
    row = result.one_or_none()
    if not row:
        msg = "The previously selected LLM model is no longer available"
        raise ApplicationError(msg, type="LLMModelNotFoundError", non_retryable=True)
    if not row.enabled:
        msg = f"LLM model '{row.name}' is disabled"
        raise ApplicationError(msg, type="LLMModelDisabledError", non_retryable=True)
    return {row.integration_id}


async def _validate_integrations(
    session: AsyncSession,
    integration_ids: set[UUID],
    expected_types: dict[UUID, str],
    project_id: str,
    node_id: str,
) -> None:
    """Check integrations exist, are in scope, are enabled, and match expected types.

    Validates in order: existence, scope, enabled, type. Scope is checked before
    enabled/type so that error messages for out-of-scope resources do not leak
    internal resource names.

    Args:
        session: Database session.
        integration_ids: UUIDs of integrations to validate.
        expected_types: Map of integration UUID to expected IntegrationType.
        project_id: Workflow's project UUID string (empty to skip scope check).
        node_id: Node ID for logging context.

    Raises:
        ApplicationError (IntegrationNotFoundError): Integration not found in the database.
        ApplicationError (IntegrationNotAccessibleError): Project-scoped integration not
            assigned to the workflow's project.
        ApplicationError (IntegrationDisabledError): Integration exists but is disabled.
        ApplicationError (IntegrationTypeMismatchError): Integration type does not match
            what the node requires (e.g. MCP server in an AAP node slot).

    """
    result = await session.execute(select(Integration).where(col(Integration.id).in_(integration_ids)))
    rows = result.scalars().all()
    found = {row.id for row in rows}

    missing = integration_ids - found
    if missing:
        msg = "One or more selected integrations are no longer available"
        raise ApplicationError(msg, type="IntegrationNotFoundError", non_retryable=True)

    if not project_id:
        logger.warning(
            "Skipping scope check: no project_id available",
            node_id=node_id,
            integration_ids=[str(iid) for iid in integration_ids],
            integration_count=len(integration_ids),
        )
    else:
        project_scoped = {row.id for row in rows if row.scope == IntegrationScope.PROJECT}
        if project_scoped:
            assigned = await session.execute(
                select(IntegrationProjectAssignment.integration_id).where(
                    col(IntegrationProjectAssignment.integration_id).in_(project_scoped),
                    IntegrationProjectAssignment.project_id == UUID(project_id),
                )
            )
            assigned_ids = set(assigned.scalars().all())
            if project_scoped - assigned_ids:
                msg = "One or more selected integrations are not accessible in this project"
                raise ApplicationError(msg, type="IntegrationNotAccessibleError", non_retryable=True)

    for row in rows:
        if not row.enabled:
            msg = f"Integration '{row.name}' is disabled"
            raise ApplicationError(msg, type="IntegrationDisabledError", non_retryable=True)

        expected = expected_types.get(row.id)
        if expected and row.integration_type != expected:
            msg = f"Integration '{row.name}' is type '{row.integration_type}', but this node requires type '{expected}'"
            raise ApplicationError(msg, type="IntegrationTypeMismatchError", non_retryable=True)


async def _validate_tools(session: AsyncSession, tool_selections: list[str]) -> None:
    """Check that all selected tools exist and are enabled.

    Args:
        session: Database session.
        tool_selections: List of tool UUID strings from the node's tool_selections field.
            Invalid UUIDs are silently skipped (best-effort validation).

    Raises:
        ApplicationError (ToolsUnavailableError): One or more selected tools are
            deleted or disabled.

    """
    valid_ids = [UUID(tid) for tid in tool_selections if _is_valid_uuid(tid)]
    if not valid_ids:
        return
    result = await session.execute(
        select(Tool.id).where(col(Tool.id).in_(valid_ids), col(Tool.enabled) == True)  # noqa: E712
    )
    available = {str(tid) for tid in result.scalars().all()}
    unavailable_count = sum(1 for tid in tool_selections if _is_valid_uuid(tid) and tid not in available)
    if unavailable_count:
        msg = f"{unavailable_count} selected tool(s) are no longer available"
        raise ApplicationError(msg, type="ToolsUnavailableError", non_retryable=True)
