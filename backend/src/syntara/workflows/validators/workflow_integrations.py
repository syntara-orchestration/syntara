"""Validate external references (integrations, LLM models, tools) in workflow definitions."""

from collections.abc import Callable, Iterable
from typing import Any
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.llm_model import LLMModel
from syntara.tool_manager.models.tool import Tool
from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

_AAP_NODE_TYPES: frozenset[str] = frozenset({NodeType.AAP_JOB_TEMPLATE, NodeType.AAP_WORKFLOW_JOB_TEMPLATE})


def _is_valid_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _extract_ids_from_nodes(
    workflow_definition: dict[str, Any],
    extractor: Callable[[dict[str, Any]], Iterable[str]],
) -> set[str]:
    """Extract valid UUIDs from node parameters using the given extractor function."""
    ids: set[str] = set()
    for node in workflow_definition.get("nodes", []):
        params = node.get("parameters", {})
        for val in extractor(params):
            if _is_valid_uuid(val):
                ids.add(val)
    return ids


def _integration_id_values(params: dict[str, Any]) -> Iterable[str]:
    """Yield integration IDs from direct integration_id and integration_connections."""
    if direct_id := params.get("integration_id"):
        yield direct_id
    for conn in params.get("integration_connections") or []:
        if conn_id := conn.get("integration_id"):
            yield conn_id


def _extract_integration_ids(workflow_definition: dict[str, Any]) -> set[str]:
    """Return integration UUIDs from node parameters. Skips template expressions."""
    return _extract_ids_from_nodes(workflow_definition, _integration_id_values)


def _extract_llm_model_ids(workflow_definition: dict[str, Any]) -> set[str]:
    """Return LLM model UUIDs from node parameters. Skips template expressions."""
    return _extract_ids_from_nodes(workflow_definition, lambda p: filter(None, [p.get("llm_model_id")]))


def _tool_selection_values(params: dict[str, Any]) -> Iterable[str]:
    """Yield tool IDs when tool_selection_strategy is SELECTED."""
    if params.get("tool_selection_strategy") != "SELECTED":
        return
    yield from params.get("tool_selections") or []


def _extract_tool_ids(workflow_definition: dict[str, Any]) -> set[str]:
    """Return tool UUIDs from nodes with SELECTED strategy. Skips template expressions."""
    return _extract_ids_from_nodes(workflow_definition, _tool_selection_values)


def _collect_expected_integration_types(workflow_definition: dict[str, Any]) -> dict[UUID, str]:
    """Build a map of integration UUID -> expected IntegrationType from node definitions."""
    ids_to_check: dict[UUID, str] = {}
    for node in workflow_definition.get("nodes", []):
        node_type = node.get("type", "")
        params = node.get("parameters", {})

        if node_type in _AAP_NODE_TYPES and _is_valid_uuid(direct_id := params.get("integration_id")):
            ids_to_check[UUID(direct_id)] = IntegrationType.ANSIBLE_AUTOMATION_PLATFORM

        if node_type == NodeType.AGENTIC:
            for conn in params.get("integration_connections") or []:
                if _is_valid_uuid(conn_id := conn.get("integration_id")):
                    ids_to_check[UUID(conn_id)] = IntegrationType.MCP_SERVER
    return ids_to_check


async def _validate_integration_types(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
) -> None:
    """Validate that referenced integrations match the expected type for each node."""
    ids_to_check = _collect_expected_integration_types(workflow_definition)
    if ids_to_check:
        result = await session.execute(
            select(Integration.id, Integration.integration_type, Integration.name).where(
                col(Integration.id).in_(ids_to_check.keys())
            )
        )
        for row in result.all():
            expected = ids_to_check.get(row.id)
            if expected and row.integration_type != expected:
                msg = (
                    f"Integration '{row.name}' is type '{row.integration_type}', "
                    f"but this node requires type '{expected}'"
                )
                raise SafeValueError(msg)

    model_ids = _extract_llm_model_ids(workflow_definition)
    if model_ids:
        parsed = [UUID(mid) for mid in model_ids]
        result = await session.execute(
            select(LLMModel.id, Integration.integration_type, Integration.name)
            .join(Integration, col(LLMModel.integration_id) == col(Integration.id))
            .where(col(LLMModel.id).in_(parsed))
        )
        for row in result.all():
            if row.integration_type != IntegrationType.LLM_PROVIDER:
                msg = (
                    f"Model's integration '{row.name}' is type '{row.integration_type}', "
                    f"but llm_model_id requires type 'llm_provider'"
                )
                raise SafeValueError(msg)


async def _validate_llm_model_references(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
) -> set[UUID]:
    """Validate that all LLM model references exist and are enabled. Returns their parent integration IDs."""
    model_ids = _extract_llm_model_ids(workflow_definition)
    if not model_ids:
        return set()
    parsed = [UUID(mid) for mid in model_ids]
    result = await session.execute(
        select(LLMModel.id, LLMModel.integration_id, LLMModel.enabled, LLMModel.name).where(
            col(LLMModel.id).in_(parsed)
        )
    )
    rows = result.all()
    found_ids = {row.id for row in rows}
    missing = {UUID(mid) for mid in model_ids} - found_ids
    if missing:
        msg = "The previously selected LLM model is no longer available"
        raise SafeValueError(msg)
    for row in rows:
        if not row.enabled:
            msg = f"LLM model '{row.name}' is disabled"
            raise SafeValueError(msg)
    return {row.integration_id for row in rows}


async def _validate_integration_scope(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
    project_id: UUID,
    extra_integration_ids: set[UUID],
) -> None:
    """Validate that all referenced integrations exist, are enabled, and are accessible in the project."""
    integration_ids = {UUID(iid) for iid in _extract_integration_ids(workflow_definition)}
    integration_ids |= extra_integration_ids

    if not integration_ids:
        return

    result = await session.execute(
        select(Integration.id, Integration.scope, Integration.enabled, Integration.name).where(
            col(Integration.id).in_(integration_ids)
        )
    )
    rows = result.all()
    found = {row.id: row.scope for row in rows}

    missing = integration_ids - set(found.keys())
    if missing:
        msg = "One or more selected integrations are no longer available"
        raise SafeValueError(msg)

    project_scoped = {iid for iid, scope in found.items() if scope == IntegrationScope.PROJECT}
    if project_scoped:
        assigned = await session.execute(
            select(IntegrationProjectAssignment.integration_id).where(
                col(IntegrationProjectAssignment.integration_id).in_(project_scoped),
                IntegrationProjectAssignment.project_id == project_id,
            )
        )
        assigned_ids = set(assigned.scalars().all())
        if project_scoped - assigned_ids:
            msg = "One or more selected integrations are not accessible in this project"
            raise SafeValueError(msg)

    for row in rows:
        if not row.enabled:
            msg = f"Integration '{row.name}' is disabled"
            raise SafeValueError(msg)


async def _clean_unavailable_tool_selections(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
) -> list[ValidationFinding]:
    """Remove unavailable (deleted or disabled) tool IDs from tool_selections in-place.

    If all selected tools are unavailable, switches tool_selection_strategy to NONE.
    Returns warning findings with node_id for each affected node.
    """
    tool_ids = _extract_tool_ids(workflow_definition)
    if not tool_ids:
        return []
    parsed = [UUID(tid) for tid in tool_ids]
    result = await session.execute(
        select(Tool.id).where(col(Tool.id).in_(parsed), col(Tool.enabled) == True)  # noqa: E712
    )
    available_ids = {str(tid) for tid in result.scalars().all()}
    unavailable_ids = tool_ids - available_ids
    if not unavailable_ids:
        return []

    findings: list[ValidationFinding] = []
    for node in workflow_definition.get("nodes", []):
        params = node.get("parameters", {})
        if params.get("tool_selection_strategy") != "SELECTED":
            continue
        selections = params.get("tool_selections") or []
        removed_count = sum(1 for tid in selections if tid in unavailable_ids)
        if not removed_count:
            continue
        cleaned = [tid for tid in selections if tid not in unavailable_ids]
        if cleaned:
            params["tool_selections"] = cleaned
        else:
            params["tool_selection_strategy"] = "NONE"
            del params["tool_selections"]
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.warning,
                category=ValidationCategory.invalid_reference,
                message=f"{removed_count} previously selected tool(s) are no longer available and were removed",
                node_id=node.get("id"),
            )
        )

    return findings


async def _extract_tool_parent_integration_ids(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
) -> set[UUID]:
    """Look up the parent integration IDs for all selected tools."""
    tool_ids = _extract_tool_ids(workflow_definition)
    if not tool_ids:
        return set()
    parsed = [UUID(tid) for tid in tool_ids]
    result = await session.execute(select(Tool.integration_id).where(col(Tool.id).in_(parsed)).distinct())
    return {iid for iid in result.scalars().all() if iid is not None}


async def validate_workflow_references(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
    project_id: UUID,
) -> list[ValidationFinding]:
    """Validate all external references in a workflow definition.

    Integrations and LLM models produce hard errors (required for node execution).
    Unavailable tools are auto-cleared with warnings (optional, node still functions).
    Parent integrations of selected tools are also checked — a disabled or out-of-scope
    integration produces a hard error even though individual tools are auto-cleared.

    Returns warning findings for any tools that were auto-cleared.
    """
    model_integration_ids = await _validate_llm_model_references(session, workflow_definition)
    tool_integration_ids = await _extract_tool_parent_integration_ids(session, workflow_definition)
    await _validate_integration_scope(
        session, workflow_definition, project_id, model_integration_ids | tool_integration_ids
    )
    await _validate_integration_types(session, workflow_definition)
    return await _clean_unavailable_tool_selections(session, workflow_definition)
