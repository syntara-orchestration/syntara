"""Validate ``mcp_tool`` node references against integrations and discovered tools.

An ``mcp_tool`` node names an integration of type ``mcp_server`` plus the tool to
invoke on it. Both halves of that reference are checked here:

* the integration must exist and be of type ``mcp_server`` (error);
* the tool name must be one of the integration's discovered tools (error), unless
  discovery has never run for that integration (warning — the operator can still
  refresh the integration before launching).

Template expressions (``${...}``) are skipped: they only resolve at execution time.
"""

from typing import Any
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.tool_manager.models.tool import Tool
from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.workflow_engine.models.workflow_definition import TEMPLATE_PATTERN, NodeType

_INTEGRATION_FIELD_PATH = "parameters.integration_id"
_TOOL_NAME_FIELD_PATH = "parameters.tool_name"


class _MCPToolReference:
    """One ``mcp_tool`` node's resolvable reference."""

    def __init__(self, node_id: str | None, integration_id: UUID, tool_name: str | None) -> None:
        self.node_id = node_id
        self.integration_id = integration_id
        self.tool_name = tool_name


def _is_template(value: Any) -> bool:  # noqa: ANN401
    return isinstance(value, str) and bool(TEMPLATE_PATTERN.search(value))


def _collect_references(workflow_definition: dict[str, Any]) -> list[_MCPToolReference]:
    """Return one reference per ``mcp_tool`` node with a literal integration UUID."""
    references: list[_MCPToolReference] = []
    for node in workflow_definition.get("nodes", []):
        if node.get("type") != NodeType.MCP_TOOL:
            continue
        params = node.get("parameters") or {}
        raw_id = params.get("integration_id")
        if not raw_id or _is_template(raw_id):
            continue
        try:
            integration_id = UUID(str(raw_id))
        except ValueError:
            continue
        raw_tool_name = params.get("tool_name")
        tool_name = None if _is_template(raw_tool_name) or not raw_tool_name else str(raw_tool_name)
        references.append(_MCPToolReference(node.get("id"), integration_id, tool_name))
    return references


def _integration_findings(
    reference: _MCPToolReference,
    integrations: dict[UUID, tuple[IntegrationType, str]],
) -> ValidationFinding | None:
    """Return an error finding when the referenced integration is missing or wrong-typed."""
    row = integrations.get(reference.integration_id)
    if row is None:
        return ValidationFinding(
            severity=ValidationSeverity.error,
            category=ValidationCategory.invalid_reference,
            message="The selected MCP server integration is no longer available",
            node_id=reference.node_id,
            field_path=_INTEGRATION_FIELD_PATH,
        )
    integration_type, name = row
    if integration_type != IntegrationType.MCP_SERVER:
        return ValidationFinding(
            severity=ValidationSeverity.error,
            category=ValidationCategory.invalid_reference,
            message=(
                f"Integration '{name}' is type '{integration_type.value}', "
                f"but an mcp_tool node requires type '{IntegrationType.MCP_SERVER.value}'"
            ),
            node_id=reference.node_id,
            field_path=_INTEGRATION_FIELD_PATH,
        )
    return None


def _tool_name_finding(
    reference: _MCPToolReference,
    integration_name: str,
    discovered_names: set[str],
) -> ValidationFinding | None:
    """Return a finding when the tool name cannot be matched to discovered tools."""
    if reference.tool_name is None:
        return None
    if not discovered_names:
        return ValidationFinding(
            severity=ValidationSeverity.warning,
            category=ValidationCategory.invalid_reference,
            message=(
                f"Integration '{integration_name}' has no discovered tools yet, so tool "
                f"'{reference.tool_name}' cannot be verified. Refresh the integration's tools."
            ),
            node_id=reference.node_id,
            field_path=_TOOL_NAME_FIELD_PATH,
        )
    if reference.tool_name not in discovered_names:
        return ValidationFinding(
            severity=ValidationSeverity.error,
            category=ValidationCategory.invalid_reference,
            message=(
                f"Tool '{reference.tool_name}' is not one of the tools discovered on integration '{integration_name}'"
            ),
            node_id=reference.node_id,
            field_path=_TOOL_NAME_FIELD_PATH,
        )
    return None


async def _load_integrations(
    session: AsyncSession,
    integration_ids: set[UUID],
) -> dict[UUID, tuple[IntegrationType, str]]:
    result = await session.execute(
        select(Integration.id, Integration.integration_type, Integration.name).where(
            col(Integration.id).in_(integration_ids)
        )
    )
    return {row.id: (row.integration_type, row.name) for row in result.all()}


async def _load_discovered_tool_names(
    session: AsyncSession,
    integration_ids: set[UUID],
) -> dict[UUID, set[str]]:
    if not integration_ids:
        return {}
    result = await session.execute(
        select(Tool.integration_id, Tool.name).where(col(Tool.integration_id).in_(integration_ids))
    )
    names: dict[UUID, set[str]] = {iid: set() for iid in integration_ids}
    for row in result.all():
        names[row.integration_id].add(row.name)
    return names


async def collect_mcp_tool_findings(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
) -> list[ValidationFinding]:
    """Validate every ``mcp_tool`` node's integration and tool-name reference.

    Returns error findings for unusable references and warning findings for
    references that cannot be verified yet.
    """
    references = _collect_references(workflow_definition)
    if not references:
        return []

    integration_ids = {ref.integration_id for ref in references}
    integrations = await _load_integrations(session, integration_ids)
    mcp_server_ids = {
        iid for iid, (itype, _) in integrations.items() if itype == IntegrationType.MCP_SERVER
    } & integration_ids
    discovered = await _load_discovered_tool_names(session, mcp_server_ids)

    findings: list[ValidationFinding] = []
    for reference in references:
        integration_finding = _integration_findings(reference, integrations)
        if integration_finding is not None:
            findings.append(integration_finding)
            continue
        _, integration_name = integrations[reference.integration_id]
        tool_finding = _tool_name_finding(
            reference,
            integration_name,
            discovered.get(reference.integration_id, set()),
        )
        if tool_finding is not None:
            findings.append(tool_finding)
    return findings
