"""Integration tests for AuditMiddleware context ID extraction.

Tests verify that the middleware correctly extracts execution_id, workflow_id,
and activity_id from URL paths and includes them in emitted audit events.
"""

# mypy: disable-error-code="attr-defined"

from collections.abc import Callable
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.events.http_request import HTTPRequestEvent, HTTPRequestHandler
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.outbox.worker import get_outbox_worker
from syntara.core.models.user import User

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


@pytest.fixture(autouse=True)
def ensure_http_request_handler_registered() -> None:
    """Ensure HTTPRequestHandler is registered before each test."""
    AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})


@pytest.mark.asyncio
async def test_middleware_extracts_path_params(
    base_client: AsyncClient,
    admin_user: User,
    create_jwt_for_user: Callable[[User], str],
) -> None:
    """Test that middleware captures execution_id and activity_id from URL path.

    POSTs to /executions/{execution_id}/activities/{activity_id}/signal endpoint,
    which will fail with 404 (no such execution), but the audit middleware should
    still emit a request_completed event with execution_id and activity_id correctly
    captured from the URL path.
    """
    # Create JWT token for admin user
    admin_token = create_jwt_for_user(admin_user)
    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    execution_id = uuid4()
    activity_id = "test-activity-123"
    signal_url = f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal"

    # Patch _build_otel_log_record to capture emitted audit events
    mock_build_otel_log_record = Mock()
    with patch("syntara.audit.outbox.worker._build_otel_log_record", new=mock_build_otel_log_record):
        # POST to signal endpoint with Authorization header (will fail with 404, but that's expected)
        response = await base_client.post(
            signal_url,
            json={"signal_data": {"action": "test", "value": 42}},
            headers=auth_headers,
        )

        # The request should fail (no such execution)
        assert response.status_code == 404

        # Flush all pending outbox writes
        await get_outbox_worker().drain()

    # Verify _build_otel_log_record was called at least once
    assert mock_build_otel_log_record.called, "Expected _build_otel_log_record to be called"

    # Find the specific POST event for our signal endpoint
    post_event = None
    for call in mock_build_otel_log_record.call_args_list:
        # Extract the AuditEvent from the call args
        audit_event: AuditEvent = call.args[0]

        if (
            audit_event.event_action == "request_completed"
            and audit_event.execution_id == execution_id
            and audit_event.activity_id == activity_id
            and audit_event.actor_id == admin_user.id
        ):
            post_event = audit_event
            break

    assert post_event is not None, (
        f"No request_completed event found for execution_id={execution_id}, "
        f"activity_id={activity_id}, actor_id={admin_user.id}. "
        f"Found {mock_build_otel_log_record.call_count} calls total."
    )

    # Verify the audit event has the correct context IDs from the URL
    assert post_event.actor_id == admin_user.id
    assert post_event.actor_username == admin_user.username
    assert post_event.actor_type == "user"
    assert post_event.execution_id == execution_id
    assert post_event.activity_id == activity_id
    assert post_event.event_action == "request_completed"
    assert post_event.event_status == "error"  # 404 response
    assert str(execution_id) in post_event.event_message


@pytest.mark.asyncio
async def test_middleware_captures_request_id_in_structured_data(
    base_client: AsyncClient,
    admin_user: User,
    create_jwt_for_user: Callable[[User], str],
) -> None:
    """Test that middleware captures X-Request-Id header and includes it in structured_data.

    Sends a request with X-Request-Id header and verifies the audit event
    contains the request_id in its structured_data field.
    """
    # Create JWT token for admin user
    admin_token = create_jwt_for_user(admin_user)
    request_id = uuid4()
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "X-Request-Id": str(request_id),
    }

    # Patch _build_otel_log_record to capture emitted audit events
    mock_build_otel_log_record = Mock()
    with patch("syntara.audit.outbox.worker._build_otel_log_record", new=mock_build_otel_log_record):
        # Make a simple GET request to any endpoint (using /api/v1/users as a valid endpoint)
        response = await base_client.get("/api/v1/users", headers=headers)
        assert response.status_code == 200

        # Flush all pending outbox writes
        await get_outbox_worker().drain()

    # Verify _build_otel_log_record was called
    assert mock_build_otel_log_record.called, "Expected _build_otel_log_record to be called"

    # Find the audit event for the GET request with our request_id
    first_get_event = None
    for call in mock_build_otel_log_record.call_args_list:
        # Extract the AuditEvent from the call args
        audit_event: AuditEvent = call.args[0]

        structured_data: AuditContextData = audit_event.structured_data or AuditContextData()
        if structured_data.request_id == str(request_id):
            first_get_event = audit_event
            break

    # Verify we found the event
    assert first_get_event is not None, "Should find audit event with matching request_id"

    # Verify the structured_data contains the request_id
    assert first_get_event.structured_data is not None
    assert first_get_event.structured_data.request_id == str(request_id)
    assert first_get_event.actor_id == admin_user.id
    assert first_get_event.actor_username == admin_user.username
    assert first_get_event.event_action == "request_completed"
    assert first_get_event.event_status == "success"  # 200 response
