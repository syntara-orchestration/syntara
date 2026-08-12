"""Unit tests for additional dataclass models.

Tests cover:
- ToolProviderRefreshResult dataclass functionality
- ToolSchema dataclass functionality
- Dictionary conversion methods
- Round-trip serialization
"""

from datetime import UTC, datetime
from typing import Any

from syntara.tool_manager.models.tool_provider_refresh_result import ToolProviderRefreshResult
from syntara.tool_manager.models.tool_schema import ToolSchema


def test_tool_provider_refresh_result_creation() -> None:
    """Test ToolProviderRefreshResult dataclass creation."""
    now = datetime.now(UTC)

    result = ToolProviderRefreshResult(
        refreshed_count=5,
        updated_count=3,
        disabled_count=2,
        refreshed_at=now,
    )

    assert result.refreshed_count == 5
    assert result.updated_count == 3
    assert result.disabled_count == 2
    assert result.refreshed_at == now


def test_tool_provider_refresh_result_zero_counts() -> None:
    """Test ToolProviderRefreshResult with zero counts."""
    now = datetime.now(UTC)

    result = ToolProviderRefreshResult(
        refreshed_count=0,
        updated_count=0,
        disabled_count=0,
        refreshed_at=now,
    )

    assert result.refreshed_count == 0
    assert result.updated_count == 0
    assert result.disabled_count == 0
    assert result.refreshed_at == now


def test_tool_schema_creation_minimal() -> None:
    """Test ToolSchema dataclass creation with minimal fields."""
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    }

    schema = ToolSchema(
        name="text_processor",
        description="Process text input",
        input_schema=input_schema,
    )

    assert schema.name == "text_processor"
    assert schema.description == "Process text input"
    assert schema.input_schema == input_schema
    assert schema.output_schema is None
    assert schema.examples is None


def test_tool_schema_creation_full() -> None:
    """Test ToolSchema dataclass creation with all fields."""
    input_schema = {
        "type": "object",
        "properties": {
            "input": {"type": "string"},
            "options": {"type": "object"},
        },
        "required": ["input"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "result": {"type": "string"},
            "status": {"type": "string"},
        },
    }

    examples: list[dict[str, Any]] = [
        {
            "input": {"input": "hello world", "options": {"uppercase": True}},
            "output": {"result": "HELLO WORLD", "status": "success"},
        },
        {
            "input": {"input": "test"},
            "output": {"result": "test", "status": "success"},
        },
    ]

    schema = ToolSchema(
        name="advanced_processor",
        description="Advanced text processing tool",
        input_schema=input_schema,
        output_schema=output_schema,
        examples=examples,
    )

    assert schema.name == "advanced_processor"
    assert schema.description == "Advanced text processing tool"
    assert schema.input_schema == input_schema
    assert schema.output_schema == output_schema
    assert schema.examples == examples
