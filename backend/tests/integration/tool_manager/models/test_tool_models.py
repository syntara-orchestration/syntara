"""Unit tests for Tool models.

Tests cover:
- Tool creation with required fields
- ToolParameter creation and relationships
- Tool validation (namespaced_name)
- Enum validation
- ToolUpdate model
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.models.tool import (
    Tool,
    ToolParameter,
    ToolParameterType,
    ToolStatus,
    ToolUpdate,
)


@pytest.mark.asyncio
async def test_create_tool_with_required_fields(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test creating a tool with all required fields."""
    tool_id = uuid4()

    tool = Tool(
        id=tool_id,
        integration_id=test_mcp_integration.id,
        name="Test Tool",
        namespaced_name="test_provider::test_tool",
        created_by=test_user.id,
    )
    test_db_session.add(tool)
    await test_db_session.commit()

    assert tool.id == tool_id
    assert tool.integration_id == test_mcp_integration.id
    assert tool.name == "Test Tool"
    assert tool.namespaced_name == "test_provider::test_tool"
    assert tool.enabled is True  # Default value
    assert tool.status == ToolStatus.AVAILABLE  # Default value
    assert tool.last_executed_at is None
    assert tool.last_refreshed_at is None
    assert tool.refresh_error is None
    assert tool.created_by == test_user.id
    assert tool.created_at is not None
    assert tool.updated_at is not None


@pytest.mark.asyncio
async def test_create_tool_with_all_fields(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test creating a tool with all fields including optional ones."""
    tool_id = uuid4()
    now = datetime.now(UTC)

    tool = Tool(
        id=tool_id,
        integration_id=test_mcp_integration.id,
        name="Full Test Tool",
        description="A test tool with all fields",
        namespaced_name="test_provider::full_test_tool",
        enabled=False,
        status=ToolStatus.ERROR,
        last_executed_at=now,
        last_refreshed_at=now,
        refresh_error="Connection failed",
        created_by=test_user.id,
        labels={"env": "test", "category": "testing"},
    )
    test_db_session.add(tool)
    await test_db_session.commit()

    assert tool.enabled is False
    assert tool.status == ToolStatus.ERROR
    assert tool.last_executed_at == now
    assert tool.last_refreshed_at == now
    assert tool.refresh_error == "Connection failed"
    assert tool.labels == {"env": "test", "category": "testing"}


def test_tool_namespaced_name_validation(test_user: User) -> None:
    """Test validation of namespaced_name field."""
    # Valid namespaced name should work
    tool = Tool(
        id=uuid4(),
        name="Test Tool",
        namespaced_name="valid_name",
        created_by=test_user.id,
    )
    assert tool.namespaced_name == "valid_name"

    # Empty string should raise ValidationError
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        Tool(
            id=uuid4(),
            name="Test Tool",
            namespaced_name="",
            created_by=test_user.id,
        )

    # Whitespace-only string should raise ValueError (passes min_length, caught by custom validator)
    with pytest.raises(ValueError, match="namespaced_name cannot be empty"):
        Tool(
            id=uuid4(),
            name="Test Tool",
            namespaced_name="   ",
            created_by=test_user.id,
        )

    # String with surrounding whitespace should be stripped
    tool = Tool(
        id=uuid4(),
        name="Test Tool",
        namespaced_name="  trimmed_name  ",
        created_by=test_user.id,
    )
    assert tool.namespaced_name == "trimmed_name"


@pytest.mark.asyncio
async def test_create_tool_parameter(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test creating a tool parameter."""
    tool_id = uuid4()
    param_id = uuid4()

    # First create a tool
    tool = Tool(
        id=tool_id,
        integration_id=test_mcp_integration.id,
        name="Test Tool",
        namespaced_name="test::tool",
        created_by=test_user.id,
    )
    test_db_session.add(tool)

    # Create a parameter
    param = ToolParameter(
        id=param_id,
        tool_id=tool_id,
        name="input_text",
        type=ToolParameterType.STRING,
        description="Input text for the tool",
        required=True,
        default_value={"value": "default"},
        example_value={"value": "example"},
        created_by=test_user.id,
    )
    test_db_session.add(param)
    await test_db_session.commit()

    assert param.id == param_id
    assert param.tool_id == tool_id
    assert param.name == "input_text"
    assert param.type == ToolParameterType.STRING
    assert param.description == "Input text for the tool"
    assert param.required is True
    assert param.default_value == {"value": "default"}
    assert param.example_value == {"value": "example"}


def test_tool_parameter_types() -> None:
    """Test ToolParameterType enum values."""
    assert ToolParameterType.STRING.value == "string"
    assert ToolParameterType.NUMBER.value == "number"
    assert ToolParameterType.BOOLEAN.value == "boolean"
    assert ToolParameterType.OBJECT.value == "object"
    assert ToolParameterType.ARRAY.value == "array"


def test_tool_status_enum() -> None:
    """Test ToolStatus enum values."""
    assert ToolStatus.AVAILABLE.value == "available"
    assert ToolStatus.MISSING.value == "missing"
    assert ToolStatus.ERROR.value == "error"


def test_tool_update_model() -> None:
    """Test ToolUpdate model."""
    update = ToolUpdate(enabled=False)
    assert update.enabled is False

    update = ToolUpdate(enabled=True)
    assert update.enabled is True


@pytest.mark.asyncio
async def test_tool_parameter_relationship(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test the relationship between Tool and ToolParameter."""
    tool_id = uuid4()

    # Create a tool
    tool = Tool(
        id=tool_id,
        integration_id=test_mcp_integration.id,
        name="Test Tool",
        namespaced_name="test::tool",
        created_by=test_user.id,
    )
    test_db_session.add(tool)

    # Create parameters for the tool
    param1 = ToolParameter(
        id=uuid4(),
        tool_id=tool_id,
        name="param1",
        type=ToolParameterType.STRING,
        description="First parameter",
        required=True,
        created_by=test_user.id,
    )
    param2 = ToolParameter(
        id=uuid4(),
        tool_id=tool_id,
        name="param2",
        type=ToolParameterType.NUMBER,
        description="Second parameter",
        required=False,
        created_by=test_user.id,
    )

    test_db_session.add_all([param1, param2])
    await test_db_session.commit()

    # sqlalchemy supports lazy-load by default
    result = await test_db_session.exec(
        select(Tool)
        .options(selectinload(Tool.parameters))  # type: ignore[arg-type]
        .where(Tool.id == tool.id)
    )
    _tool = result.first()

    # Check relationship
    assert _tool is not None
    assert len(_tool.parameters) == 2
    param_names = {p.name for p in _tool.parameters}
    assert param_names == {"param1", "param2"}

    # Verify parameter types
    param_types = {p.type for p in _tool.parameters}
    assert param_types == {ToolParameterType.STRING, ToolParameterType.NUMBER}

    # Verify each parameter references the correct tool
    for param in _tool.parameters:
        assert param.tool_id == tool_id


@pytest.mark.asyncio
async def test_tool_cascade_delete_parameters(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test that deleting a Tool cascades to delete its ToolParameters."""
    # Create parameters for the existing test tool
    param1 = ToolParameter(
        id=uuid4(),
        tool_id=test_tool.id,
        name="param1",
        type=ToolParameterType.STRING,
        description="First parameter",
        required=True,
        created_by=test_user.id,
    )
    param2 = ToolParameter(
        id=uuid4(),
        tool_id=test_tool.id,
        name="param2",
        type=ToolParameterType.BOOLEAN,
        description="Second parameter",
        required=False,
        created_by=test_user.id,
    )

    test_db_session.add_all([param1, param2])
    await test_db_session.commit()

    # Verify parameters exist
    params_result = await test_db_session.exec(select(ToolParameter).where(ToolParameter.tool_id == test_tool.id))
    params = params_result.all()
    assert len(params) == 2

    # Delete the tool
    await test_db_session.delete(test_tool)
    await test_db_session.commit()

    # Verify parameters are cascade deleted
    params_after_delete = await test_db_session.exec(select(ToolParameter).where(ToolParameter.tool_id == test_tool.id))
    assert len(params_after_delete.all()) == 0


@pytest.mark.asyncio
async def test_tool_namespaced_name_unique_constraint(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test that Tool.namespaced_name unique constraint works correctly."""
    # Create first tool with a specific namespaced_name
    tool1 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Test Tool",
        namespaced_name="test_provider::unique_tool",
        created_by=test_user.id,
    )
    test_db_session.add(tool1)
    await test_db_session.commit()

    # Try to create another tool with the same namespaced_name (should fail)
    tool2 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Another Tool",
        namespaced_name="test_provider::unique_tool",  # Same namespaced_name (should fail)
        created_by=test_user.id,
    )
    test_db_session.add(tool2)

    # Should raise IntegrityError due to unique constraint violation
    with pytest.raises((IntegrityError, Exception), match=r".*unique.*|.*constraint.*"):
        await test_db_session.commit()


@pytest.mark.asyncio
async def test_tool_namespaced_name_different_names_allowed(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test that different namespaced_names are allowed for the same integration."""
    # Create multiple tools with different namespaced_names (should work)
    tool1 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Tool One",
        namespaced_name="test_provider::tool_one",
        created_by=test_user.id,
    )
    tool2 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Tool Two",
        namespaced_name="test_provider::tool_two",
        created_by=test_user.id,
    )

    test_db_session.add_all([tool1, tool2])
    await test_db_session.commit()  # Should succeed

    # Verify both tools were created successfully
    assert tool1.namespaced_name == "test_provider::tool_one"
    assert tool2.namespaced_name == "test_provider::tool_two"


@pytest.mark.asyncio
async def test_tool_namespaced_name_case_sensitivity(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test that tool namespaced_names are case-sensitive for uniqueness."""
    # Create first tool with lowercase namespaced_name
    tool1 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Tool One",
        namespaced_name="test::tool",
        created_by=test_user.id,
    )
    test_db_session.add(tool1)
    await test_db_session.commit()

    # Create second tool with different case (should work - case sensitive)
    tool2 = Tool(
        id=uuid4(),
        integration_id=test_mcp_integration.id,
        name="Tool Two",
        namespaced_name="Test::Tool",  # Different case
        created_by=test_user.id,
    )
    test_db_session.add(tool2)
    await test_db_session.commit()  # Should succeed

    # Verify both tools exist with their respective namespaced_names
    assert tool1.namespaced_name == "test::tool"
    assert tool2.namespaced_name == "Test::Tool"
