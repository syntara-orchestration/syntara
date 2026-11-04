"""Unit tests for FormPromptsApiClient.

Tests HTTP client for Forms API including:
- Form prompt creation
- Listing form prompts by execution
- Batch expiration
- Batch cancellation
- Retry logic for transient errors
- Error handling for client/server errors
"""

from typing import Any
from uuid import uuid4

import httpx
import pytest

from syntara.workflows.clients.form_prompts_client import (
    FormPromptsApiClient,
    FormPromptsApiClientConnectionError,
    FormPromptsApiClientError,
)


@pytest.fixture
def client() -> FormPromptsApiClient:
    """FormPromptsApiClient configured for testing with fast retries."""
    return FormPromptsApiClient(
        base_url="http://test-api:8000/api/v1",
        timeout=5.0,
        max_retries=2,
        retry_backoff_base=0.01,
    )


@pytest.fixture
def create_request_data() -> dict[str, Any]:
    """Sample form prompt creation request as dict."""
    return {
        "execution_id": str(uuid4()),
        "prompt_node_id": "form1",
        "name": "User Input Form",
        "form_definition": {"fields": []},
        "project_id": str(uuid4()),
    }


@pytest.fixture
def form_prompt_response_data() -> dict[str, Any]:
    """Sample form prompt API response data."""
    return {
        "id": str(uuid4()),
        "execution_id": str(uuid4()),
        "prompt_node_id": "form1",
        "name": "User Input Form",
        "status": "pending",
        "form_definition": {"fields": []},
        "timeout_at": None,
        "created_at": "2026-04-09T12:00:00Z",
        "updated_at": "2026-04-09T12:00:00Z",
    }


@pytest.mark.asyncio
async def test_create_form_prompt_success(
    client: FormPromptsApiClient,
    create_request_data: dict[str, Any],
    form_prompt_response_data: dict[str, Any],
) -> None:
    """Test successful form prompt creation."""
    mock_response = httpx.Response(201, json=form_prompt_response_data)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    result = await client.create_form_prompt(create_request_data)

    assert result["id"] == form_prompt_response_data["id"]
    assert result["status"] == "pending"
    assert result["prompt_node_id"] == "form1"


@pytest.mark.asyncio
async def test_create_form_prompt_client_error(
    client: FormPromptsApiClient,
    create_request_data: dict[str, Any],
) -> None:
    """Test 4xx errors are not retried and raise FormPromptsApiClientError."""
    mock_response = httpx.Response(409, json={"detail": "Already exists"})
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return mock_response

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    with pytest.raises(FormPromptsApiClientError) as exc_info:
        await client.create_form_prompt(create_request_data)

    assert exc_info.value.status_code == 409
    assert call_count == 1  # No retries for 4xx


@pytest.mark.asyncio
async def test_create_form_prompt_retries_on_5xx(
    client: FormPromptsApiClient,
    create_request_data: dict[str, Any],
    form_prompt_response_data: dict[str, Any],
) -> None:
    """Test that 5xx errors trigger retries."""
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"detail": "Service unavailable"})
        return httpx.Response(201, json=form_prompt_response_data)

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    result = await client.create_form_prompt(create_request_data)
    assert result["prompt_node_id"] == "form1"
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_create_form_prompt_connection_error(
    client: FormPromptsApiClient,
    create_request_data: dict[str, Any],
) -> None:
    """Test connection failures raise FormPromptsApiClientConnectionError."""

    def handler(_: httpx.Request) -> httpx.Response:
        msg = "Connection refused"
        raise httpx.ConnectError(msg)

    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.base_url)

    with pytest.raises(FormPromptsApiClientConnectionError):
        await client.create_form_prompt(create_request_data)


@pytest.mark.asyncio
async def test_list_form_prompts_by_execution(
    client: FormPromptsApiClient,
    form_prompt_response_data: dict[str, Any],
) -> None:
    """Test listing form prompts filtered by execution_id."""
    list_response = {
        "resources": [form_prompt_response_data],
        "next": None,
    }
    mock_response = httpx.Response(200, json=list_response)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    results = await client.list_form_prompts_by_execution(uuid4())
    assert len(results) == 1
    assert results[0]["prompt_node_id"] == "form1"


@pytest.mark.asyncio
async def test_batch_expire_success(client: FormPromptsApiClient) -> None:
    """Test batch expiration."""
    prompt_ids = [uuid4(), uuid4()]
    batch_response = {
        "results": [{"prompt_id": str(pid), "success": True} for pid in prompt_ids],
        "total_success": 2,
        "total_failed": 0,
    }
    mock_response = httpx.Response(200, json=batch_response)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    result = await client.batch_expire(prompt_ids)
    assert result["total_success"] == 2
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_batch_expire_empty_list(client: FormPromptsApiClient) -> None:
    """Test batch expiration with empty list returns immediately."""
    result = await client.batch_expire([])
    assert result["total_success"] == 0
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_batch_cancel_success(client: FormPromptsApiClient) -> None:
    """Test batch cancellation."""
    prompt_ids = [uuid4(), uuid4()]
    batch_response = {
        "results": [{"prompt_id": str(pid), "success": True} for pid in prompt_ids],
        "total_success": 2,
        "total_failed": 0,
    }
    mock_response = httpx.Response(200, json=batch_response)
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: mock_response), base_url=client.base_url
    )

    result = await client.batch_cancel(prompt_ids)
    assert result["total_success"] == 2
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_batch_cancel_empty_list(client: FormPromptsApiClient) -> None:
    """Test batch cancellation with empty list returns immediately."""
    result = await client.batch_cancel([])
    assert result["total_success"] == 0
    assert result["total_failed"] == 0


@pytest.mark.asyncio
async def test_context_manager(client: FormPromptsApiClient) -> None:
    """Test async context manager closes client."""
    async with client as c:
        assert c is client
    # Client should be closed after exiting context
    assert client.http_client.is_closed
