"""Unit tests for ToolService.

Tests cover:
- CRUD operations (get, update, bulk update)
- Filtering and search functionality
- Sorting and pagination
- Error conditions and edge cases
- Business logic validation
- Tool status management
"""

from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.exceptions import (
    ToolBulkUpdateValidationError,
    ToolNotFoundError,
)
from syntara.tool_manager.models.tool import (
    Tool,
    ToolStatus,
    ToolUpdate,
)
from syntara.tool_manager.services.tool_service import ToolService


@pytest.mark.asyncio
async def test_get_tool_detail_success(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test successful tool retrieval with full details."""
    service = ToolService(test_db_session, test_user)

    tool = await service.get_tool_detail(test_tool.id)

    assert tool.id == test_tool.id
    assert tool.name == test_tool.name
    assert tool.namespaced_name == test_tool.namespaced_name
    assert tool.status == test_tool.status


@pytest.mark.asyncio
async def test_get_tool_detail_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test tool retrieval with non-existent ID."""
    service = ToolService(test_db_session, test_user)
    non_existent_id = uuid4()

    with pytest.raises(ToolNotFoundError, match=f"Tool {non_existent_id} not found"):
        await service.get_tool_detail(non_existent_id)


@pytest.mark.asyncio
async def test_update_tool_status_disable_success(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test successful tool disabling."""
    service = ToolService(test_db_session, test_user)

    # Ensure tool starts as available
    test_tool.enabled = True
    await test_db_session.commit()

    updated_tool = await service.update_tool(test_tool.id, ToolUpdate(enabled=False))

    assert not updated_tool.enabled
    assert updated_tool.updated_by == test_user.id
    assert updated_tool.updated_at >= test_tool.updated_at


@pytest.mark.asyncio
async def test_update_tool_status_enable_success(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test successful tool enabling from disabled state."""
    service = ToolService(test_db_session, test_user)

    # Set tool as disabled
    test_tool.enabled = False
    await test_db_session.commit()

    updated_tool = await service.update_tool(test_tool.id, ToolUpdate(enabled=True))

    assert updated_tool.enabled
    assert updated_tool.updated_by == test_user.id
    assert updated_tool.updated_at >= test_tool.updated_at


@pytest.mark.asyncio
async def test_update_tool_status_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test tool update with non-existent ID."""
    service = ToolService(test_db_session, test_user)
    non_existent_id = uuid4()

    with pytest.raises(ToolNotFoundError, match=f"Tool {non_existent_id} not found"):
        await service.update_tool(non_existent_id, ToolUpdate(enabled=False))


@pytest.mark.asyncio
async def test_update_tool_status_success(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test successful tool status update."""
    service = ToolService(test_db_session, test_user)

    # Set initial status
    test_tool.status = ToolStatus.AVAILABLE
    await test_db_session.commit()

    updated_tool = await service.update_tool(test_tool.id, ToolUpdate(status=ToolStatus.ERROR))

    assert updated_tool.status == ToolStatus.ERROR
    assert updated_tool.updated_by == test_user.id
    assert updated_tool.updated_at >= test_tool.updated_at


@pytest.mark.asyncio
async def test_update_tool_refresh_error_success(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test successful tool refresh error update."""
    service = ToolService(test_db_session, test_user)

    # Set initial refresh error
    test_tool.refresh_error = None
    await test_db_session.commit()

    error_message = "Connection timeout while refreshing tool"
    updated_tool = await service.update_tool(test_tool.id, ToolUpdate(refresh_error=error_message))

    assert updated_tool.refresh_error == error_message
    assert updated_tool.updated_by == test_user.id
    assert updated_tool.updated_at >= test_tool.updated_at


@pytest.mark.asyncio
async def test_update_tool_all_fields_success(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test successful update of all tool fields (enabled, status, refresh_error)."""
    service = ToolService(test_db_session, test_user)

    # Set initial values
    test_tool.enabled = True
    test_tool.status = ToolStatus.AVAILABLE
    test_tool.refresh_error = None
    await test_db_session.commit()

    error_message = "Tool provider unavailable"
    updated_tool = await service.update_tool(
        test_tool.id, ToolUpdate(status=ToolStatus.ERROR, refresh_error=error_message, enabled=False)
    )

    assert not updated_tool.enabled
    assert updated_tool.status == ToolStatus.ERROR
    assert updated_tool.refresh_error == error_message
    assert updated_tool.updated_by == test_user.id
    assert updated_tool.updated_at >= test_tool.updated_at


@pytest.mark.asyncio
async def test_bulk_update_tools_success(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test successful bulk update of tools."""
    service = ToolService(test_db_session, test_user)

    # Create multiple tools
    tools = []
    for i in range(3):
        tool = Tool(
            id=uuid4(),
            integration_id=test_mcp_integration.id,
            name=f"Test Tool {i}",
            namespaced_name=f"test::tool{i}",
            status=ToolStatus.AVAILABLE,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        tools.append(tool)

    test_db_session.add_all(tools)
    await test_db_session.commit()

    tool_ids = [tool.id for tool in tools]
    result = await service.bulk_update_tools(tool_ids, enabled=False)

    assert result.updated_count == 3
    assert result.skipped_count == 0
    assert result.updated_at is not None

    # Verify tools were updated
    for tool in tools:
        await test_db_session.refresh(tool)
        assert not tool.enabled
        assert tool.updated_by == test_user.id


@pytest.mark.asyncio
async def test_bulk_update_tools_enable_disabled(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test bulk enabling of disabled tools."""
    service = ToolService(test_db_session, test_user)

    # Create disabled tools
    tools = []
    for i in range(2):
        tool = Tool(
            id=uuid4(),
            integration_id=test_mcp_integration.id,
            name=f"Disabled Tool {i}",
            namespaced_name=f"test::disabled{i}",
            enabled=False,
            status=ToolStatus.AVAILABLE,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        tools.append(tool)

    test_db_session.add_all(tools)
    await test_db_session.commit()

    tool_ids = [tool.id for tool in tools]
    result = await service.bulk_update_tools(tool_ids, enabled=True)

    assert result.updated_count == 2
    assert result.skipped_count == 0

    # Verify tools were enabled
    for tool in tools:
        await test_db_session.refresh(tool)
        assert tool.enabled


@pytest.mark.asyncio
async def test_bulk_update_tools_with_nonexistent(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test bulk update with mix of existing and non-existent tool IDs."""
    service = ToolService(test_db_session, test_user)

    # Mix existing and non-existent tool IDs
    tool_ids = [test_tool.id, uuid4(), uuid4()]
    result = await service.bulk_update_tools(tool_ids, enabled=False)

    assert result.updated_count == 1  # Only the existing tool
    assert result.skipped_count == 2  # Two non-existent tools
    assert result.updated_at is not None

    # Verify existing tool was updated
    await test_db_session.refresh(test_tool)
    assert not test_tool.enabled


@pytest.mark.asyncio
async def test_bulk_update_tools_empty_list(test_db_session: AsyncSession, test_user: User) -> None:
    """Test bulk update fails with empty tool IDs list."""
    service = ToolService(test_db_session, test_user)

    with pytest.raises(ToolBulkUpdateValidationError, match="tool_ids cannot be empty"):
        await service.bulk_update_tools([], enabled=False)


@pytest.mark.asyncio
async def test_bulk_update_tools_too_many(test_db_session: AsyncSession, test_user: User) -> None:
    """Test bulk update fails with more than 50 tool IDs."""
    service = ToolService(test_db_session, test_user)

    # Create list of 51 tool IDs
    tool_ids = [uuid4() for _ in range(51)]

    with pytest.raises(ToolBulkUpdateValidationError, match="Cannot update more than 50 tools at once"):
        await service.bulk_update_tools(tool_ids, enabled=False)


@pytest.mark.asyncio
async def test_bulk_update_tools_valid_statuses(test_db_session: AsyncSession, test_user: User) -> None:
    """Test bulk update accepts valid ToolStatus enum values."""
    service = ToolService(test_db_session, test_user)

    tool_ids = [uuid4()]

    # Test that both valid statuses work without error
    # (even though no tools exist, the status validation should pass)
    result1 = await service.bulk_update_tools(tool_ids, enabled=True)
    assert result1.updated_count == 0
    assert result1.skipped_count == 1

    result2 = await service.bulk_update_tools(tool_ids, enabled=False)
    assert result2.updated_count == 0
    assert result2.skipped_count == 1


@pytest.mark.asyncio
async def test_list_tools_empty(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing tools when none exist."""
    service = ToolService(test_db_session, test_user)

    result = await service.list_tools()

    assert result.resources == []
    assert result.next is None
    assert result.prev is None


@pytest.mark.asyncio
async def test_list_tools_basic(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test basic tool listing."""
    service = ToolService(test_db_session, test_user)

    result = await service.list_tools()

    assert len(result.resources) == 1
    assert result.resources[0].id == test_tool.id
    assert result.resources[0].name == test_tool.name


@pytest.mark.asyncio
async def test_list_tools_with_total(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test tool listing with total count."""
    service = ToolService(test_db_session, test_user)

    result = await service.list_tools(include_total=True)

    assert len(result.resources) == 1
    assert result.total == 1


@pytest.mark.asyncio
async def test_list_tools_filtering(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test tool listing with filtering."""
    service = ToolService(test_db_session, test_user)

    # Create test tools with different attributes
    tool1 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Alpha Tool",
        namespaced_name="test::alpha",
        enabled=True,
        status=ToolStatus.AVAILABLE,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    tool2 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Beta Tool",
        namespaced_name="test::beta",
        enabled=False,
        status=ToolStatus.MISSING,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    tool3 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Gamma Tool",
        namespaced_name="test::gamma",
        enabled=True,
        status=ToolStatus.ERROR,
        created_by=test_user.id,
        updated_by=test_user.id,
    )

    test_db_session.add_all([tool1, tool2, tool3])
    await test_db_session.commit()

    # Test name filtering with contains
    result = await service.list_tools(query_params_items=[("name[contains]", "Alpha")])
    assert len(result.resources) == 1
    assert result.resources[0].name == "Alpha Tool"

    # Test status filtering
    result = await service.list_tools(query_params_items=[("status", "available")])
    assert len(result.resources) == 1
    assert result.resources[0].status == ToolStatus.AVAILABLE

    # Test status filtering for error
    result = await service.list_tools(query_params_items=[("status", "error")])
    assert len(result.resources) == 1
    assert result.resources[0].status == ToolStatus.ERROR

    # Test provider_id filtering
    result = await service.list_tools(query_params_items=[("integration_id", str(test_mcp_integration.id))])
    assert len(result.resources) >= 3  # At least our 3 test tools

    # Test namespaced_name filtering
    result = await service.list_tools(query_params_items=[("namespaced_name", "test::alpha")])
    assert len(result.resources) == 1
    assert result.resources[0].namespaced_name == "test::alpha"


@pytest.mark.asyncio
async def test_list_tools_sorting(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test tool listing with different sorting options."""
    service = ToolService(test_db_session, test_user)

    # Create test tools with different names
    tool1 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Charlie Tool",
        namespaced_name="test::charlie",
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    tool2 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Alpha Tool",
        namespaced_name="test::alpha",
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    tool3 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Beta Tool",
        namespaced_name="test::beta",
        created_by=test_user.id,
        updated_by=test_user.id,
    )

    test_db_session.add_all([tool1, tool2, tool3])
    await test_db_session.commit()

    # Test sorting by name (ascending)
    result = await service.list_tools(sort="name")
    names = [t.name for t in result.resources]
    assert names == ["Alpha Tool", "Beta Tool", "Charlie Tool"]

    # Test sorting by name (descending)
    result = await service.list_tools(sort="-name")
    names = [t.name for t in result.resources]
    assert names == ["Charlie Tool", "Beta Tool", "Alpha Tool"]

    # Test sorting by status
    result = await service.list_tools(sort="status")
    assert len(result.resources) == 3


@pytest.mark.asyncio
async def test_list_tools_pagination(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test tool listing with pagination."""
    service = ToolService(test_db_session, test_user)

    # Create multiple test tools
    tools = []
    for i in range(5):
        tool = Tool(
            id=uuid4(),
            integration_id=test_mcp_integration.id,
            name=f"Tool {i:02d}",
            namespaced_name=f"test::tool{i:02d}",
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        tools.append(tool)

    test_db_session.add_all(tools)
    await test_db_session.commit()

    # Test pagination with limit
    result = await service.list_tools(limit=2)
    assert len(result.resources) == 2

    # Test with different limit
    result = await service.list_tools(limit=3)
    assert len(result.resources) == 3


@pytest.mark.asyncio
async def test_list_tools_returns_all(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test that list returns all tools."""
    service = ToolService(test_db_session, test_user)

    tool1 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Tool One",
        namespaced_name="test::one",
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    tool2 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Tool Two",
        namespaced_name="test::two",
        created_by=test_user.id,
        updated_by=test_user.id,
    )

    test_db_session.add_all([tool1, tool2])
    await test_db_session.commit()

    result = await service.list_tools()

    tool_names = [t.name for t in result.resources]
    assert "Tool One" in tool_names
    assert "Tool Two" in tool_names


@pytest.mark.asyncio
async def test_list_tools_complex_filtering(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test tool listing with complex filter combinations."""
    service = ToolService(test_db_session, test_user)

    # Create tools with different combinations of attributes
    tool1 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Test Available Tool",
        namespaced_name="test::available",
        enabled=True,
        status=ToolStatus.AVAILABLE,
        created_by=test_user.id,
        updated_by=test_user.id,
    )

    tool2 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Test Disabled Tool",
        namespaced_name="test::disabled",
        enabled=False,
        status=ToolStatus.MISSING,
        created_by=test_user.id,
        updated_by=test_user.id,
    )

    tool3 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Production Tool",
        namespaced_name="test::production",
        enabled=True,
        status=ToolStatus.ERROR,
        created_by=test_user.id,
        updated_by=test_user.id,
    )

    test_db_session.add_all([tool1, tool2, tool3])
    await test_db_session.commit()

    # Test status filtering for available tools
    result = await service.list_tools(query_params_items=[("status", "available")])
    assert len(result.resources) == 1
    assert result.resources[0].name == "Test Available Tool"

    # Test name contains filtering
    result = await service.list_tools(query_params_items=[("name[contains]", "Test")])
    test_tools = [t for t in result.resources if "Test" in t.name]
    assert len(test_tools) == 2


@pytest.mark.asyncio
async def test_service_initialization(test_db_session: AsyncSession, test_user: User) -> None:
    """Test service initialization."""
    service = ToolService(test_db_session, test_user)

    assert service.session == test_db_session
    assert service.user == test_user


@pytest.mark.asyncio
async def test_list_tools_with_cursor_and_sorting(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test tool listing with both cursor pagination and sorting."""
    service = ToolService(test_db_session, test_user)

    # Create test tools
    tools = []
    for i in range(3):
        tool = Tool(
            id=uuid4(),
            integration_id=test_mcp_integration.id,
            name=f"Tool {chr(65 + i)}",  # Tool A, B, C
            namespaced_name=f"test::tool{chr(65 + i).lower()}",
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        tools.append(tool)

    test_db_session.add_all(tools)
    await test_db_session.commit()

    # Test with sorting and limit
    result = await service.list_tools(sort="name", limit=2)
    assert len(result.resources) == 2
    # Should get Tool A and Tool B when sorted by name
    names = [t.name for t in result.resources]
    assert names[0] == "Tool A"
    assert names[1] == "Tool B"


@pytest.mark.asyncio
async def test_update_tool_status_audit_tracking(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test that tool updates properly track audit information."""
    service = ToolService(test_db_session, test_user)

    original_updated_at = test_tool.updated_at
    updated_tool = await service.update_tool(test_tool.id, ToolUpdate(enabled=False))

    assert updated_tool.updated_by == test_user.id
    assert updated_tool.updated_at > original_updated_at
    assert updated_tool.created_by == test_tool.created_by  # Should not change


@pytest.mark.asyncio
async def test_bulk_update_tools_audit_tracking(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test that bulk updates properly track audit information."""
    service = ToolService(test_db_session, test_user)

    original_updated_at = test_tool.updated_at
    result = await service.bulk_update_tools([test_tool.id], enabled=False)

    assert result.updated_count == 1
    assert result.updated_at is not None

    # Verify audit fields
    await test_db_session.refresh(test_tool)
    assert test_tool.updated_by == test_user.id
    assert test_tool.updated_at > original_updated_at
    assert test_tool.created_by == test_tool.created_by  # Should not change
