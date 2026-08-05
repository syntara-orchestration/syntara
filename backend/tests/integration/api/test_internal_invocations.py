"""Integration tests for internal invocation endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_internal_create_invocation_returns_202(
    auth_client_with_mocked_llm: AsyncClient, test_project_id: str
) -> None:
    """POST /_internal/invocations returns 202 Accepted."""
    response = await auth_client_with_mocked_llm.post(
        "/_internal/invocations",
        json={
            "prompt": "Internal endpoint test",
            "sessionId": "internal-session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["status"] in ["created", "running"]
    assert data["prompt"] == "Internal endpoint test"


@pytest.mark.asyncio
async def test_internal_create_invocation_validates_request(
    auth_client_with_mocked_llm: AsyncClient, test_project_id: str
) -> None:
    """POST /_internal/invocations rejects invalid payloads."""
    response = await auth_client_with_mocked_llm.post(
        "/_internal/invocations",
        json={"prompt": "Missing session_id", "project_id": test_project_id},
    )

    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_internal_get_invocation_returns_200(
    auth_client_with_mocked_llm: AsyncClient, test_project_id: str
) -> None:
    """GET /_internal/invocations/{id} returns the invocation."""
    create_response = await auth_client_with_mocked_llm.post(
        "/_internal/invocations",
        json={
            "prompt": "Get test",
            "sessionId": "get-session-001",
            "project_id": test_project_id,
        },
    )
    assert create_response.status_code == 202
    invocation_id = create_response.json()["id"]

    get_response = await auth_client_with_mocked_llm.get(
        f"/_internal/invocations/{invocation_id}",
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == invocation_id


@pytest.mark.asyncio
async def test_internal_get_invocation_returns_404_for_missing(
    auth_client_with_mocked_llm: AsyncClient,
) -> None:
    """GET /_internal/invocations/{id} returns 404 for unknown ID."""
    response = await auth_client_with_mocked_llm.get(
        "/_internal/invocations/00000000-0000-0000-0000-000000000000",
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_public_invocations_endpoint_not_found(
    auth_client_with_mocked_llm: AsyncClient, test_project_id: str
) -> None:
    """POST /api/v1/invocations returns 404 or 405 after privatization."""
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        json={
            "prompt": "Should not work",
            "sessionId": "session-001",
            "project_id": test_project_id,
        },
    )
    assert response.status_code in (404, 405)
