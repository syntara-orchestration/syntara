"""Integration tests for internal invocation create endpoint."""

import pytest
from httpx import AsyncClient

from tests.integration.helpers.invocations import wait_for_invocation_execution

INVOCATIONS_URL = "/_internal/invocations"


@pytest.mark.asyncio
async def test_invoke_accepts_camel_case_field_names(
    auth_client_with_mocked_llm: AsyncClient, test_project_id: str
) -> None:
    """Test that POST /_internal/invocations accepts camelCase aliases sessionId and contextData."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "camelCase aliases test",
            "sessionId": "camel-session-001",
            "project_id": test_project_id,
            "contextData": {"environment": "staging"},
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["session_id"] == "camel-session-001"
    assert data["context_data"] == {"environment": "staging"}


@pytest.mark.asyncio
async def test_multipart_request_rejected_by_json_endpoint(
    auth_client_with_mocked_llm: AsyncClient, test_project_id: str
) -> None:
    """Test that POST /_internal/invocations rejects multipart/form-data requests."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        data={
            "prompt": "multipart body",
            "session_id": "form-session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invoke_returns_202_accepted(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test that POST /_internal/invocations returns 202 Accepted status."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "Deploy app to production",
            "created_by": str(test_user.id),
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_invoke_response_schema(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test that response matches expected schema."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "Deploy app to production",
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code == 202
    data = response.json()
    invocation_id = data["id"]

    async with wait_for_invocation_execution(auth_client_with_mocked_llm, invocation_id) as final_data:
        data = final_data or data

    assert "id" in data
    assert "status" in data
    assert "created_at" in data
    assert "created_by" in data
    assert "prompt" in data
    assert "session_id" in data

    assert isinstance(data["id"], str)
    assert data["status"] in ["running", "completed", "failed"]
    assert isinstance(data["created_at"], str)
    assert data["created_by"] == str(test_user.id)
    assert data["prompt"] == "Deploy app to production"
    assert data["session_id"] == "session-001"
    assert "project_id" in data
    assert data["project_id"] == test_project_id


@pytest.mark.asyncio
async def test_invoke_with_context(auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str) -> None:
    """Test invocation request with context data."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "Deploy app",
            "session_id": "session-001",
            "project_id": test_project_id,
            "context_data": {"environment": "production", "file_metadata": [], "region": "us-east-1"},
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["context_data"] == {"environment": "production", "file_metadata": [], "region": "us-east-1"}


@pytest.mark.asyncio
async def test_invoke_validation_missing_session_id(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test validation error for missing session_id."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "Deploy app",
            "created_by": str(test_user.id),
            "project_id": test_project_id,
        },
    )

    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_invoke_validation_missing_prompt(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test validation error for missing prompt."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "created_by": str(test_user.id),
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_invoke_validation_empty_prompt(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test validation error for empty prompt."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "",
            "created_by": str(test_user.id),
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_invoke_validation_missing_project_id(auth_client_with_mocked_llm: AsyncClient, test_user) -> None:
    """Test validation error for missing project_id."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "Deploy app",
            "session_id": "session-001",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invoke_with_very_long_prompt(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test invocation with very long prompt (near max length)."""
    long_prompt = "Deploy application " * 500  # ~9000 chars

    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": long_prompt,
            "created_by": str(test_user.id),
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["prompt"] == long_prompt


@pytest.mark.asyncio
async def test_invoke_validation_prompt_exceeds_max_length(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test validation error for prompt exceeding max length (10000 chars)."""
    too_long_prompt = "a" * 10001

    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": too_long_prompt,
            "created_by": str(test_user.id),
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_invoke_response_includes_all_fields(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test that POST response includes all expected fields including inherited ones."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "Complete field test",
            "created_by": str(test_user.id),
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code == 202
    data = response.json()

    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "labels" in data
    assert "created_by" in data
    assert "updated_by" in data
    assert "prompt" in data
    assert "session_id" in data
    assert "status" in data
    assert "started_at" in data
    assert "completed_at" in data
    assert "context_data" in data
    assert "result" in data
    assert "error_message" in data
    assert "checkpoint_data" in data


@pytest.mark.asyncio
async def test_invoke_null_fields_handling(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Test that null/optional fields are properly returned as null."""
    response = await auth_client_with_mocked_llm.post(
        INVOCATIONS_URL,
        json={
            "prompt": "Null field test",
            "created_by": str(test_user.id),
            "session_id": "session-001",
            "project_id": test_project_id,
        },
    )

    assert response.status_code == 202
    data = response.json()
    invocation_id = data["id"]

    assert data["status"] == "created"
    assert data["started_at"] is None
    assert data["completed_at"] is None
    assert data["result"] is None
    assert data["error_message"] is None

    async with wait_for_invocation_execution(auth_client_with_mocked_llm, invocation_id) as final_data:
        data = final_data or data

    assert data["status"] in ["running", "completed"]
    assert data["started_at"] is not None

    if data["status"] == "completed":
        assert data["completed_at"] is not None
        assert data["result"] is not None
        assert data["error_message"] is None
    else:
        assert data["completed_at"] is None

    assert data["checkpoint_data"] is None
    assert data["updated_by"] is None
