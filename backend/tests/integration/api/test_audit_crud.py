"""Integration tests for CRUD operation audit events.

Tests verify that database INSERT, UPDATE, and DELETE operations
automatically generate audit events via Postgres triggers.

CRUD events are sent to OTEL (not Postgres), so these tests mock
the OTEL emitter and verify it was called with the correct events.
Uses the tools table (tool_providers table has been dropped).
"""

# mypy: disable-error-code="attr-defined"

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.context_managers import actor_context
from syntara.audit.models.audit_event import AuditEvent
from syntara.audit.outbox.worker import get_outbox_worker
from syntara.core.models.user import User
from syntara.tool_manager.models.tool import Tool, ToolStatus

TOOL_NAME: str = str(uuid4())


def _find_audit_event(
    mock_otel_emit: MagicMock,
    event_action: str,
    resource_id: str | None = None,
    resource_name: str | None = None,
) -> AuditEvent:
    """Find an audit event in OTEL mock calls by action and optional filters.

    Args:
        mock_otel_emit: The mocked OTEL emit function
        event_action: The event action to filter by (e.g., "tool_create")
        resource_id: Optional resource ID to match in structured_data
        resource_name: Optional resource name to match on the event

    Returns:
        The matching AuditEvent

    Raises:
        AssertionError: If no matching event is found

    """
    for call in mock_otel_emit.call_args_list:
        event: AuditEvent = call[0][0]
        if event.event_action != event_action:
            continue

        if resource_id is not None and event.structured_data.resource_id != resource_id:
            continue

        if resource_name is not None and event.resource_name != resource_name:
            continue

        return event

    filters = f"event_action={event_action}"
    if resource_id:
        filters += f", resource_id={resource_id}"
    if resource_name:
        filters += f", resource_name={resource_name}"
    msg = f"No audit event found matching: {filters}"
    raise AssertionError(msg)


@pytest_asyncio.fixture(autouse=True)
async def audit_metadata_populated(test_db_session: AsyncSession) -> None:
    """Ensure audit_table_metadata is populated for tools.

    While setup_audit_metadata() runs during migrations and creates the metadata,
    the test database uses transaction-based isolation where each test runs in a
    rolled-back transaction. The metadata INSERTs from migrations are committed
    at the session level, but individual test transactions may not see them due
    to isolation. This fixture ensures metadata is visible within each test's
    transaction scope.
    """
    await test_db_session.execute(
        text("""
            INSERT INTO audit_table_metadata (table_name, model_name, audit_level, auditable_fields)
            VALUES ('tools', 'Tool', 'full', NULL)
            ON CONFLICT (table_name) DO NOTHING
        """)
    )
    await test_db_session.commit()


@pytest_asyncio.fixture
async def test_tool_for_audit(
    test_mcp_integration,
    test_db_session: AsyncSession,
    test_user: User,
) -> Tool:
    """Create a Tool for audit testing.

    Create as a separate fixture to ensure the session is committed before
    the test exits. Fixture test_db_session commits when the function exits.
    """
    with actor_context(actor=test_user):
        tool = Tool(
            name=TOOL_NAME,
            namespaced_name=f"mock::{TOOL_NAME}",
            integration_id=test_mcp_integration.id,
            enabled=True,
            status=ToolStatus.AVAILABLE,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        test_db_session.add(tool)
        await test_db_session.commit()

    return tool


@pytest.mark.asyncio
@patch("syntara.audit.outbox.worker._build_otel_log_record")
async def test_create_generates_audit_event(
    mock_build_otel_log_record: MagicMock,
    test_tool_for_audit: Tool,
    session_app: FastAPI,
    test_user: User,
) -> None:
    """Test that creating a Tool generates a CRUD audit event.

    The fixture creates a Tool and commits the session, which triggers
    the CRUD audit trigger. This test verifies that:
    1. A CRUD audit event was generated for the INSERT operation
    2. The audit event contains correct operation type, model name, and actor info
    """
    # Flush all pending AuditEventRecord writes
    await get_outbox_worker().drain()

    # Find the Tool create event among all emitted events
    emitted_event = _find_audit_event(mock_build_otel_log_record, event_action="tool_create", resource_name=TOOL_NAME)

    # Verify the audit event has correct fields
    assert emitted_event.actor_id == test_user.id
    assert emitted_event.actor_username == test_user.username
    assert emitted_event.actor_type == "user"
    assert emitted_event.event_action == "tool_create"
    assert emitted_event.event_category == "system_operation"
    assert emitted_event.event_status == "success"
    assert emitted_event.event_message == "Tool created"
    assert emitted_event.source_component == "database.trigger"

    # Verify structured data contains CRUD operation details
    structured_data = emitted_event.structured_data
    assert structured_data.data_type == "crud_operation"
    assert structured_data.operation == "create"
    assert structured_data.model_name == "Tool"
    assert structured_data.resource_id == str(test_tool_for_audit.id)

    # For create operations, resource_data should contain a snapshot of the new object
    assert hasattr(structured_data, "resource_data")
    resource_data = structured_data.resource_data
    assert resource_data["name"] == test_tool_for_audit.name


@pytest.mark.asyncio
@patch("syntara.audit.outbox.worker._build_otel_log_record")
async def test_update_generates_audit_event(
    mock_build_otel_log_record: MagicMock,
    test_tool_for_audit: Tool,
    session_app: FastAPI,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating a Tool generates a CRUD audit event with field changes."""
    with actor_context(actor=test_user):
        test_tool_for_audit.refresh_error = "updated error"
        test_db_session.add(test_tool_for_audit)
        await test_db_session.commit()
        await test_db_session.refresh(test_tool_for_audit)

    # Flush all pending AuditEventRecord writes
    await get_outbox_worker().drain()

    # Find the Tool update event among all emitted events
    emitted_event = _find_audit_event(
        mock_build_otel_log_record, event_action="tool_update", resource_id=str(test_tool_for_audit.id)
    )

    # Verify the audit event has correct fields
    assert emitted_event.actor_id == test_user.id
    assert emitted_event.event_action == "tool_update"
    assert emitted_event.event_message == "Tool updated"
    assert emitted_event.source_component == "database.trigger"

    # Verify structured data contains CRUD operation details
    structured_data = emitted_event.structured_data
    assert structured_data.data_type == "crud_operation"
    assert structured_data.operation == "update"
    assert structured_data.model_name == "Tool"
    assert structured_data.resource_id == str(test_tool_for_audit.id)

    # UPDATE operations should have changes
    assert hasattr(structured_data, "changes")


@pytest.mark.asyncio
@patch("syntara.audit.outbox.worker._build_otel_log_record")
async def test_delete_generates_audit_event(
    mock_build_otel_log_record: MagicMock,
    test_tool_for_audit: Tool,
    session_app: FastAPI,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleting a Tool generates a CRUD audit event with final snapshot."""
    tool_id = test_tool_for_audit.id

    with actor_context(actor=test_user):
        await test_db_session.delete(test_tool_for_audit)
        await test_db_session.commit()

    # Flush all pending AuditEventRecord writes
    await get_outbox_worker().drain()

    # Find the Tool delete event among all emitted events
    emitted_event = _find_audit_event(mock_build_otel_log_record, event_action="tool_delete", resource_id=str(tool_id))

    # Verify the audit event has correct fields
    assert emitted_event.actor_id == test_user.id
    assert emitted_event.event_action == "tool_delete"
    assert emitted_event.event_message == "Tool deleted"
    assert emitted_event.source_component == "database.trigger"

    # Verify structured data contains CRUD operation details
    structured_data = emitted_event.structured_data
    assert structured_data.data_type == "crud_operation"
    assert structured_data.operation == "delete"
    assert structured_data.model_name == "Tool"
    assert structured_data.resource_id == str(tool_id)

    # For delete operations, resource_data should contain final snapshot
    assert hasattr(structured_data, "resource_data")
    resource_data = structured_data.resource_data
    assert resource_data["id"] == str(tool_id)
    assert resource_data["name"] == TOOL_NAME
