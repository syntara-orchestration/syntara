"""Unit tests for tool filtering functions.

Tests filtering LangChain BaseTools by Tool.enabled field and enhancing
tools with metadata, using (integration_id, name) matching.
"""

from unittest.mock import Mock
from uuid import uuid4

from langchain_core.tools import BaseTool

from syntara.agent_orchestrator.tool_manager import tool_filtering
from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool
from syntara.tool_manager.models.tool import ToolStatus, ToolWithParameters


class TestToolFiltering:
    """Test tool filtering by enabled status using (integration_id, name) matching."""

    def test_filter_base_tools_by_enabled_tools(
        self, mock_namespaced_tools: list[NamespacedBaseTool], sample_tools: list[ToolWithParameters]
    ) -> None:
        """Test filtering NamespacedBaseTools by enabled ToolWithParameters using (integration_id, name)."""
        filtered_tools = tool_filtering.filter_base_tools_by_enabled(
            namespaced_tools=mock_namespaced_tools, enabled_tools=sample_tools
        )

        # Should only return NamespacedBaseTools that match enabled ToolWithParameters
        assert len(filtered_tools) == 2
        base_tools = [nbt.base_tool for nbt in filtered_tools]
        assert base_tools[0].name == "code_search"
        assert base_tools[1].name == "file_read"

    def test_filter_preserves_base_tool_objects(
        self, mock_namespaced_tools: list[NamespacedBaseTool], sample_tools: list[ToolWithParameters]
    ) -> None:
        """Test that filtering returns original NamespacedBaseTool instances, not copies."""
        filtered_tools = tool_filtering.filter_base_tools_by_enabled(
            namespaced_tools=mock_namespaced_tools, enabled_tools=sample_tools
        )

        # Should be original NamespacedBaseTool instances that were in the input
        for filtered_tool in filtered_tools:
            assert filtered_tool in mock_namespaced_tools
            assert isinstance(filtered_tool, NamespacedBaseTool)

        # Verify that the BaseTool objects within are the same objects as in original
        original_base_tools = [nbt.base_tool for nbt in mock_namespaced_tools]
        for nbt in filtered_tools:
            assert nbt.base_tool in original_base_tools

    def test_empty_lists_handling(self) -> None:
        """Test handling of empty tool lists."""
        # Test empty NamespacedTools
        result1 = tool_filtering.filter_base_tools_by_enabled(namespaced_tools=[], enabled_tools=[])
        assert result1 == []

        # Test empty enabled tools with a non-empty namespaced tools list
        dummy_tool = Mock(spec=BaseTool)
        dummy_tool.name = "test_tool"
        dummy_namespaced_tool = NamespacedBaseTool(
            integration_id=uuid4(),
            integration_name="test",
            tool_name="test_tool",
            base_tool=dummy_tool,
        )

        result2 = tool_filtering.filter_base_tools_by_enabled(
            namespaced_tools=[dummy_namespaced_tool], enabled_tools=[]
        )
        assert result2 == []

    def test_enhance_namespaced_tools_with_metadata(self) -> None:
        """Test that enhance_namespaced_tools_with_metadata adds tool_id to BaseTool metadata."""
        integration_id = uuid4()

        # Create sample BaseTools with namespacing
        tool1 = Mock(spec=BaseTool)
        tool1.name = "tool1"
        tool1.metadata = None  # Initially no metadata

        tool2 = Mock(spec=BaseTool)
        tool2.name = "tool2"
        tool2.metadata = {}  # Initially empty metadata

        # Create NamespacedBaseTools
        namespaced_tools = [
            NamespacedBaseTool(
                integration_id=integration_id,
                integration_name="provider1",
                tool_name="tool1",
                base_tool=tool1,
            ),
            NamespacedBaseTool(
                integration_id=integration_id,
                integration_name="provider1",
                tool_name="tool2",
                base_tool=tool2,
            ),
        ]

        # Create corresponding enabled ToolWithParameters
        tool1_id = uuid4()
        tool2_id = uuid4()
        user_id = uuid4()
        enabled_tools = [
            ToolWithParameters(
                id=tool1_id,
                name="tool1",
                namespaced_name="provider1::tool1",
                description="Tool 1",
                integration_id=integration_id,
                enabled=True,
                status=ToolStatus.AVAILABLE,
                parameters=[],
                created_by=user_id,
            ),
            ToolWithParameters(
                id=tool2_id,
                name="tool2",
                namespaced_name="provider1::tool2",
                description="Tool 2",
                integration_id=integration_id,
                enabled=True,
                status=ToolStatus.AVAILABLE,
                parameters=[],
                created_by=user_id,
            ),
        ]

        enhanced_tools = tool_filtering.enhance_namespaced_tools_with_metadata(namespaced_tools, enabled_tools)

        # Should return both tools with tool_id in metadata
        assert len(enhanced_tools) == 2

        # Find specific tools and verify their metadata
        tool1_enhanced = next(tool for tool in enhanced_tools if tool.name == "tool1")
        tool2_enhanced = next(tool for tool in enhanced_tools if tool.name == "tool2")

        assert hasattr(tool1_enhanced, "metadata")
        assert tool1_enhanced.metadata is not None
        assert tool1_enhanced.metadata.get("tool_id") == str(tool1_id)

        assert hasattr(tool2_enhanced, "metadata")
        assert tool2_enhanced.metadata is not None
        assert tool2_enhanced.metadata.get("tool_id") == str(tool2_id)

    def test_rename_mismatch_filter_and_metadata(self) -> None:
        """Regression test for AAP-79781: tool matching works after integration rename.

        When an integration is renamed (DB has OldName::tool, live is NewName::tool),
        filtering and metadata enhancement must still work via (integration_id, name)
        and metadata must carry the DB namespaced_name for metrics resolution.
        """
        integration_id = uuid4()
        tool_id = uuid4()
        user_id = uuid4()

        # Live MCP returns the tool under the NEW integration name
        live_tool = Mock(spec=BaseTool)
        live_tool.name = "summarize"
        live_tool.metadata = None

        namespaced_tools = [
            NamespacedBaseTool(
                integration_id=integration_id,
                integration_name="NewName",
                tool_name="summarize",
                base_tool=live_tool,
            ),
        ]

        # DB still has the OLD integration name in namespaced_name
        enabled_tools = [
            ToolWithParameters(
                id=tool_id,
                name="summarize",
                namespaced_name="OldName::summarize",
                description="Summarize text",
                integration_id=integration_id,
                enabled=True,
                status=ToolStatus.AVAILABLE,
                parameters=[],
                created_by=user_id,
            ),
        ]

        # filter_base_tools_by_enabled should match on (integration_id, name)
        filtered = tool_filtering.filter_base_tools_by_enabled(namespaced_tools, enabled_tools)
        assert len(filtered) == 1
        assert filtered[0].base_tool is live_tool

        # enhance should set tool_id and use the DB namespaced_name (not the live one)
        enhanced = tool_filtering.enhance_namespaced_tools_with_metadata(namespaced_tools, enabled_tools)
        assert len(enhanced) == 1
        metadata = enhanced[0].metadata
        assert metadata is not None
        assert metadata["tool_id"] == str(tool_id)
        assert metadata["namespaced_name"] == "OldName::summarize"
        assert metadata["integration_id"] == str(integration_id)
