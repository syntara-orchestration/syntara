"""Unit tests for ApprovalsApiClient.

Tests HTTP client for Approvals API including:
- Approval creation
- Listing approvals by execution
- Batch cancellation
- Retry logic for transient errors
- Error handling for client/server errors
"""

from typing import Any
from uuid import uuid4

import httpx
import pytest

from syntara.workflows.clients.approvals_client import (
    ApprovalsApiClient,
    ApprovalsApiClientConnectionError,
    ApprovalsApiClientError,
)


@pytest.fixture
def client() -> ApprovalsApiClient:
    """ApprovalsApiClient configured for testing with fast retries."""
    return ApprovalsApiClient(
        base_url="http://test-api:8000/api/v1",
        timeout=5.0,
        max_retries=2,
        retry_backoff_base=0.01,
    )


@pytest.fixture
def create_request_data() -> dict[str, Any]:
    """Sample approval creation request as dict."""
    return {
        "execution_id": str(uuid4()),
        "approval_node_id": "review_step",
        "name": "Approve deployment",
        "timeout_at": None,
        "next_step_approved": {"id": "deploy", "name": "Deploy", "type": "task"},
        "next_step_rejected": None,
        "workflow_context": {
            "workflow_id": str(uuid4()),
            "workflow_name": "Deploy Pipeline",
            "inputs": {"env": "prod"},
            "previous_step": None,
        },
    }


@pytest.fixture
def approval_response_data() -> dict[str, Any]:
    """Sample approval API response data."""
    return {
        "id": str(uuid4()),
        "execution_id": str(uuid4()),
        "approval_node_id": "review_step",
        "name": "Approve deployment",
        "status": "pending",
        "timeout_at": None,
        "next_step_approved": {"id": "deploy", "name": "Deploy", "type": "task"},
        "next_step_rejected": None,
        "workflow_context": {
            "workflow_id": str(uuid4()),
            "workflow_name": "Deploy Pipeline",
            "inputs": {"env": "prod"},
            "previous_step": None,
        },
        "decided_by": None,
        "decided_at": None,
        "decision_notes": None,
        "created_at": "2026-04-09T12:00:00Z",
        "updated_at": "2026-04-09T12:00:00Z",
    }


@pytest.mark.asyncio
async def test_create_approval_success(
    client: ApprovalsApiClient,
    create_request_data: dict[str, Any],
    approval_response_data: dict[str, Any],
) -> None:
    """Test successful approval creation."""
    mock_response = httpx.Response(201, json=approval_response_data)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    result = await client.create_approval(create_request_data)

    assert result["id"] == approval_response_data["id"]
    assert result["status"] == "pending"
    assert result["approval_node_id"] == "review_step"


@pytest.mark.asyncio
async def test_create_approval_client_error(
    client: ApprovalsApiClient,
    create_request_data: dict[str, Any],
) -> None:
    """Test 4xx errors are not retried and raise ApprovalsApiClientError."""
    mock_response = httpx.Response(409, json={"detail": "Already exists"})
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return mock_response

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    with pytest.raises(ApprovalsApiClientError) as exc_info:
        await client.create_approval(create_request_data)

    assert exc_info.value.status_code == 409
    assert call_count == 1  # No retries for 4xx


@pytest.mark.asyncio
async def test_create_approval_retries_on_5xx(
    client: ApprovalsApiClient,
    create_request_data: dict[str, Any],
    approval_response_data: dict[str, Any],
) -> None:
    """Test that 5xx errors trigger retries."""
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"detail": "Service unavailable"})
        return httpx.Response(201, json=approval_response_data)

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    result = await client.create_approval(create_request_data)
    assert result["approval_node_id"] == "review_step"
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_create_approval_connection_error(
    client: ApprovalsApiClient,
    create_request_data: dict[str, Any],
) -> None:
    """Test connection failures raise ApprovalsApiClientConnectionError."""

    def handler(_: httpx.Request) -> httpx.Response:
        msg = "Connection refused"
        raise httpx.ConnectError(msg)

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    with pytest.raises(ApprovalsApiClientConnectionError):
        await client.create_approval(create_request_data)


@pytest.mark.asyncio
async def test_list_approvals_by_execution(
    client: ApprovalsApiClient,
    approval_response_data: dict[str, Any],
) -> None:
    """Test listing approvals filtered by execution_id."""
    list_response = {
        "resources": [approval_response_data],
        "next": None,
    }
    mock_response = httpx.Response(200, json=list_response)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    results = await client.list_approvals_by_execution(uuid4())
    assert len(results) == 1
    assert results[0]["approval_node_id"] == "review_step"


@pytest.mark.asyncio
async def test_list_approvals_pagination(
    client: ApprovalsApiClient,
    approval_response_data: dict[str, Any],
) -> None:
    """Test paginated listing."""
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"resources": [approval_response_data], "next": "cursor1"})
        return httpx.Response(200, json={"resources": [approval_response_data], "next": None})

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    results = await client.list_approvals_by_execution(uuid4(), limit_per_page=1)
    assert len(results) == 2
    assert call_count == 2


@pytest.mark.asyncio
async def test_list_approvals_retries_on_5xx(
    client: ApprovalsApiClient,
    approval_response_data: dict[str, Any],
) -> None:
    """Test that 5xx errors during listing trigger retries."""
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"detail": "Service unavailable"})
        return httpx.Response(200, json={"resources": [approval_response_data], "next": None})

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    results = await client.list_approvals_by_execution(uuid4())
    assert len(results) == 1
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_list_approvals_empty_page_with_cursor(
    client: ApprovalsApiClient,
    approval_response_data: dict[str, Any],
) -> None:
    """Test that empty pages during pagination are handled correctly."""
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"resources": [], "next": "cursor1"})
        return httpx.Response(200, json={"resources": [approval_response_data], "next": None})

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    results = await client.list_approvals_by_execution(uuid4(), limit_per_page=1)
    assert len(results) == 1  # Only item from second page
    assert call_count == 2


@pytest.mark.asyncio
async def test_batch_cancel_retries_on_5xx(client: ApprovalsApiClient) -> None:
    """Test that 5xx errors during batch cancel trigger retries."""
    approval_ids = [uuid4(), uuid4()]
    call_count = 0
    batch_response = {
        "results": [
            {"approval_id": str(aid), "success": True, "status": "cancelled", "error": None} for aid in approval_ids
        ],
        "total_success": 2,
        "total_failed": 0,
    }

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"detail": "Service unavailable"})
        return httpx.Response(200, json=batch_response)

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    result = await client.batch_cancel(approval_ids)
    assert result["total_success"] == 2
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_batch_cancel_success(client: ApprovalsApiClient) -> None:
    """Test batch cancellation."""
    approval_ids = [uuid4(), uuid4()]
    batch_response = {
        "results": [
            {"approval_id": str(aid), "success": True, "status": "cancelled", "error": None} for aid in approval_ids
        ],
        "total_success": 2,
        "total_failed": 0,
    }
    mock_response = httpx.Response(200, json=batch_response)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    result = await client.batch_cancel(approval_ids)
    assert result["total_success"] == 2
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_batch_cancel_empty_list(client: ApprovalsApiClient) -> None:
    """Test batch cancellation with empty list returns immediately."""
    result = await client.batch_cancel([])
    assert result["total_success"] == 0
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_batch_expire_success(client: ApprovalsApiClient) -> None:
    """Test batch expiration."""
    approval_ids = [uuid4(), uuid4()]
    batch_response = {
        "results": [
            {"approval_id": str(aid), "success": True, "status": "expired", "error": None} for aid in approval_ids
        ],
        "total_success": 2,
        "total_failed": 0,
    }
    mock_response = httpx.Response(200, json=batch_response)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    result = await client.batch_expire(approval_ids)
    assert result["total_success"] == 2
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_batch_expire_empty_list(client: ApprovalsApiClient) -> None:
    """Test batch expiration with empty list returns immediately."""
    result = await client.batch_expire([])
    assert result["total_success"] == 0
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_batch_expire_sends_expired_status(client: ApprovalsApiClient) -> None:
    """Test that batch expire sends 'expired' status in request body."""
    approval_ids = [uuid4()]
    captured_request = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "results": [{"approval_id": str(approval_ids[0]), "success": True, "status": "expired", "error": None}],
                "total_success": 1,
                "total_failed": 0,
            },
        )

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    await client.batch_expire(approval_ids)

    assert captured_request is not None
    import json

    body = json.loads(captured_request.content)
    assert body["decisions"][0]["status"] == "expired"


@pytest.mark.asyncio
async def test_context_manager(client: ApprovalsApiClient) -> None:
    """Test async context manager closes client."""
    async with client as c:
        assert c is client
    # Client should be closed after exiting context
    assert client.http_client.is_closed
