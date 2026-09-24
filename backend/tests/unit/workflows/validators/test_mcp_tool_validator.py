"""Unit tests for mcp_tool node reference validation."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from syntara.integrations.models.integration import IntegrationType
from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.validators.mcp_tool import _collect_references, collect_mcp_tool_findings


class _Row:
    """Stand-in for a SQLAlchemy result row with named columns."""

    def __init__(self, **fields: Any) -> None:  # noqa: ANN401
        for key, value in fields.items():
            setattr(self, key, value)


class _Result:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def all(self) -> list[_Row]:
        return self._rows


def _session(
    integrations: list[_Row],
    tools: list[_Row] | None = None,
) -> AsyncMock:
    """Build a mock session returning integration rows then tool rows."""
    session = AsyncMock()
    session.execute.side_effect = [_Result(integrations), _Result(tools or [])]
    return session


def _integration_row(integration_id: UUID, name: str = "mcp-1", itype: IntegrationType | None = None) -> _Row:
    return _Row(id=integration_id, integration_type=itype or IntegrationType.MCP_SERVER, name=name)


def _definition(integration_id: str, tool_name: str = "echo", node_id: str = "n1") -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": node_id,
                "type": "mcp_tool",
                "parameters": {"integration_id": integration_id, "tool_name": tool_name},
            }
        ]
    }


class TestCollectReferences:
    """_collect_references only picks up resolvable mcp_tool references."""

    def test_ignores_other_node_types(self) -> None:
        definition = {"nodes": [{"id": "n1", "type": "http_request", "parameters": {"integration_id": str(uuid4())}}]}
        assert _collect_references(definition) == []

    def test_skips_template_integration_id(self) -> None:
        assert _collect_references(_definition("${trigger.integration_id}")) == []

    def test_skips_non_uuid_integration_id(self) -> None:
        assert _collect_references(_definition("not-a-uuid")) == []

    def test_template_tool_name_is_unverifiable(self) -> None:
        references = _collect_references(_definition(str(uuid4()), tool_name="${trigger.tool}"))
        assert len(references) == 1
        assert references[0].tool_name is None

    def test_handles_missing_nodes_key(self) -> None:
        assert _collect_references({}) == []


@pytest.mark.asyncio
class TestCollectMCPToolFindings:
    """collect_mcp_tool_findings emits findings per broken reference."""

    async def test_no_findings_for_definition_without_mcp_tool_nodes(self) -> None:
        session = _session([])
        findings = await collect_mcp_tool_findings(session, {"nodes": []})
        assert findings == []
        session.execute.assert_not_called()

    async def test_no_findings_when_tool_is_discovered(self) -> None:
        integration_id = uuid4()
        session = _session(
            [_integration_row(integration_id)],
            [_Row(integration_id=integration_id, name="echo")],
        )
        findings = await collect_mcp_tool_findings(session, _definition(str(integration_id)))
        assert findings == []

    async def test_error_when_tool_not_discovered(self) -> None:
        integration_id = uuid4()
        session = _session(
            [_integration_row(integration_id)],
            [_Row(integration_id=integration_id, name="other_tool")],
        )
        findings = await collect_mcp_tool_findings(session, _definition(str(integration_id)))
        assert len(findings) == 1
        finding = findings[0]
        assert finding.severity == ValidationSeverity.error
        assert finding.category == ValidationCategory.invalid_reference
        assert finding.node_id == "n1"
        assert finding.field_path == "parameters.tool_name"
        assert "echo" in finding.message

    async def test_warning_when_integration_has_no_discovered_tools(self) -> None:
        integration_id = uuid4()
        session = _session([_integration_row(integration_id)], [])
        findings = await collect_mcp_tool_findings(session, _definition(str(integration_id)))
        assert len(findings) == 1
        assert findings[0].severity == ValidationSeverity.warning
        assert findings[0].category == ValidationCategory.invalid_reference
        assert findings[0].field_path == "parameters.tool_name"

    async def test_error_when_integration_missing(self) -> None:
        session = _session([], [])
        findings = await collect_mcp_tool_findings(session, _definition(str(uuid4())))
        assert len(findings) == 1
        assert findings[0].severity == ValidationSeverity.error
        assert findings[0].field_path == "parameters.integration_id"

    async def test_error_when_integration_is_wrong_type(self) -> None:
        integration_id = uuid4()
        session = _session(
            [_integration_row(integration_id, name="llm-1", itype=IntegrationType.LLM_PROVIDER)],
            [],
        )
        findings = await collect_mcp_tool_findings(session, _definition(str(integration_id)))
        assert len(findings) == 1
        assert findings[0].severity == ValidationSeverity.error
        assert findings[0].field_path == "parameters.integration_id"
        assert "mcp_server" in findings[0].message

    async def test_template_tool_name_produces_no_finding(self) -> None:
        integration_id = uuid4()
        session = _session([_integration_row(integration_id)], [])
        findings = await collect_mcp_tool_findings(
            session, _definition(str(integration_id), tool_name="${trigger.tool}")
        )
        assert findings == []

    async def test_reports_one_finding_per_node(self) -> None:
        integration_id = uuid4()
        definition: dict[str, Any] = {
            "nodes": [
                _definition(str(integration_id), tool_name="missing_a", node_id="n1")["nodes"][0],
                _definition(str(integration_id), tool_name="missing_b", node_id="n2")["nodes"][0],
            ]
        }
        session = _session(
            [_integration_row(integration_id)],
            [_Row(integration_id=integration_id, name="echo")],
        )
        findings = await collect_mcp_tool_findings(session, definition)
        assert {f.node_id for f in findings} == {"n1", "n2"}
        assert all(f.severity == ValidationSeverity.error for f in findings)
