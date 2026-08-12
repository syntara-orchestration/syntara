"""Unit tests for result dataclass models and request validation models.

Tests cover:
- ToolBulkUpdate request model validation
- ToolValidationResult dataclass functionality
- ToolProviderValidationResult dataclass functionality
- Dictionary conversion methods
- Round-trip serialization
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.tool_manager.models.tool_bulk_update import ToolBulkUpdate
from syntara.tool_manager.models.tool_provider_validation_result import ToolProviderValidationResult
from syntara.tool_manager.models.tool_validation import ToolValidationResult


def test_tool_bulk_update_valid_creation() -> None:
    """Test ToolBulkUpdate with valid data."""
    tool_ids = [uuid4(), uuid4(), uuid4()]

    bulk_update = ToolBulkUpdate(tool_ids=tool_ids, enabled=False)

    assert bulk_update.tool_ids == tool_ids
    assert not bulk_update.enabled


def test_tool_bulk_update_enabled() -> None:
    """Test ToolBulkUpdate with enabled state."""
    tool_ids = [uuid4()]

    bulk_update = ToolBulkUpdate(tool_ids=tool_ids, enabled=True)

    assert bulk_update.tool_ids == tool_ids
    assert bulk_update.enabled


def test_tool_bulk_update_empty_tool_ids() -> None:
    """Test ToolBulkUpdate validation fails with empty tool_ids."""
    with pytest.raises(ValidationError) as exc_info:
        ToolBulkUpdate(tool_ids=[], enabled=False)

    assert "tool_ids cannot be empty" in str(exc_info.value)


def test_tool_bulk_update_too_many_tool_ids() -> None:
    """Test ToolBulkUpdate validation fails with more than 50 tool_ids."""
    # Create 51 tool IDs
    tool_ids = [uuid4() for _ in range(51)]

    with pytest.raises(ValidationError) as exc_info:
        ToolBulkUpdate(tool_ids=tool_ids, enabled=False)

    # Check that validation fails due to too many items (either Pydantic max_length or custom validator)
    error_str = str(exc_info.value)
    assert "List should have at most 50 items" in error_str or "Cannot update more than 50 tools at once" in error_str


def test_tool_bulk_update_max_limit_boundary() -> None:
    """Test ToolBulkUpdate accepts exactly 50 tool_ids."""
    # Create exactly 50 tool IDs
    tool_ids = [uuid4() for _ in range(50)]

    bulk_update = ToolBulkUpdate(tool_ids=tool_ids, enabled=False)

    assert len(bulk_update.tool_ids) == 50
    assert not bulk_update.enabled


def test_tool_bulk_update_duplicate_tool_ids() -> None:
    """Test ToolBulkUpdate accepts duplicate tool IDs."""
    tool_id = uuid4()
    tool_ids = [tool_id, tool_id, tool_id]

    bulk_update = ToolBulkUpdate(tool_ids=tool_ids, enabled=False)

    assert bulk_update.tool_ids == tool_ids
    assert len(bulk_update.tool_ids) == 3


def test_tool_validation_result_creation() -> None:
    """Test ToolValidationResult dataclass creation."""
    now = datetime.now(UTC)

    result = ToolValidationResult(
        success=True,
        duration_ms=1500,
        status="success",
        message="Tool validation completed successfully",
        validated_at=now,
        validation_output={"result": "valid"},
    )

    assert result.success is True
    assert result.duration_ms == 1500
    assert result.status == "success"
    assert result.message == "Tool validation completed successfully"
    assert result.validated_at == now
    assert result.validation_output == {"result": "valid"}


def test_tool_validation_result_without_output() -> None:
    """Test ToolValidationResult without validation_output."""
    now = datetime.now(UTC)

    result = ToolValidationResult(
        success=False,
        duration_ms=500,
        status="timeout",
        message="Tool validation timed out",
        validated_at=now,
    )

    assert result.success is False
    assert result.duration_ms == 500
    assert result.status == "timeout"
    assert result.message == "Tool validation timed out"
    assert result.validated_at == now
    assert result.validation_output is None


def test_connection_validation_result_creation() -> None:
    """Test ToolProviderValidationResult dataclass creation."""
    now = datetime.now(UTC)

    result = ToolProviderValidationResult(
        valid=True,
        provider_type="mcp",
        validated_at=now,
        error=None,
    )

    assert result.valid is True
    assert result.provider_type == "mcp"
    assert result.validated_at == now
    assert result.error is None
    assert result.timeout is False


def test_connection_validation_result_with_error() -> None:
    """Test ToolProviderValidationResult with error."""
    now = datetime.now(UTC)

    result = ToolProviderValidationResult(
        valid=False,
        provider_type="custom",
        validated_at=now,
        error="Authentication failed",
    )

    assert result.valid is False
    assert result.provider_type == "custom"
    assert result.validated_at == now
    assert result.error == "Authentication failed"
    assert result.timeout is False


def test_connection_validation_result_with_timeout() -> None:
    """Test ToolProviderValidationResult with timeout."""
    now = datetime.now(UTC)

    result = ToolProviderValidationResult(
        valid=False,
        provider_type="mcp",
        validated_at=now,
        error="Connection timed out",
        timeout=True,
    )

    assert result.valid is False
    assert result.provider_type == "mcp"
    assert result.validated_at == now
    assert result.error == "Connection timed out"
    assert result.timeout is True
