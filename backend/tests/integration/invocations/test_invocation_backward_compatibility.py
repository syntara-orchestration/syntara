"""Contract tests for backward compatibility of POST /invocations (JSON-only endpoint).

These tests validate:
- application/json requests still work without files
- context_data is empty object when no files (no file_ids key)
- multipart/form-data is rejected — file uploads must use POST /invocations/chat

NOTE: POST /invocations is JSON-only. Multipart requests (with or without files)
must be sent to POST /invocations/chat instead.
"""

import pytest
from httpx import AsyncClient

from syntara.core.constants import CONTEXT_KEY, CONTEXT_KEY_FILE_IDS


@pytest.mark.asyncio
async def test_json_request_without_files_succeeds(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test that application/json requests still work without files.

    Validates:
    - JSON content-type requests succeed
    - No regression in existing invocation API
    """
    # Arrange
    payload = {
        "prompt": "What is the weather today?",
        "session_id": "backward-compat-001",
        "project_id": str(test_project_id),
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        json=payload,
    )

    # Assert
    assert response.status_code == 202
    response_data = response.json()
    assert "id" in response_data
    assert response_data["prompt"] == "What is the weather today?"


@pytest.mark.asyncio
async def test_json_request_context_data_empty_without_files(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test that context_data is empty object when no files uploaded.

    Validates:
    - context_data field exists but is empty
    - No file_ids field when no files (AAP-60780)
    """
    # Arrange
    payload = {
        "prompt": "Test context data",
        "session_id": "backward-compat-002",
        "project_id": str(test_project_id),
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        json=payload,
    )

    # Assert
    assert response.status_code == 202
    response_data = response.json()
    assert CONTEXT_KEY in response_data
    # With AAP-60780, context_data is empty when no files are uploaded
    assert response_data[CONTEXT_KEY] == {}
    assert CONTEXT_KEY_FILE_IDS not in response_data[CONTEXT_KEY]


@pytest.mark.asyncio
async def test_json_request_with_existing_context_data(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test that existing context_data functionality still works.

    Validates:
    - Can still pass context_data in JSON payload
    - file_ids not added when no files (AAP-60780)
    """
    # Arrange
    payload = {
        "prompt": "Test with context",
        "session_id": "backward-compat-003",
        "project_id": str(test_project_id),
        CONTEXT_KEY: {
            "environment": "production",
            "region": "us-east-1",
        },
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        json=payload,
    )

    # Assert
    assert response.status_code == 202
    response_data = response.json()
    assert CONTEXT_KEY in response_data
    # With AAP-60780, user-provided context_data is preserved without file_ids when no files
    assert response_data[CONTEXT_KEY] == {
        "environment": "production",
        "region": "us-east-1",
    }
    assert CONTEXT_KEY_FILE_IDS not in response_data[CONTEXT_KEY]


@pytest.mark.asyncio
async def test_multipart_rejected_by_json_endpoint(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test that POST /invocations rejects multipart/form-data requests.

    Validates:
    - The JSON-only endpoint does not accept multipart form submissions
    - Clients must use POST /invocations/chat for file uploads
    """
    # Arrange
    data = {
        "prompt": "Multipart payload",
        "session_id": "backward-compat-rejection-001",
        "project_id": str(test_project_id),
    }

    # Act — send as multipart/form-data (httpx uses this when `data=` is passed)
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        data=data,
    )

    # Assert — FastAPI returns 422 when the body cannot be parsed as JSON
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_multipart_request_without_files_compatible(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test that POST /invocations/chat without files works as expected.

    Validates:
    - Multipart requests can omit files parameter on the /chat endpoint
    - context_data is empty when no files are uploaded (AAP-60780)
    """
    # Arrange
    data = {
        "prompt": "Multipart without files",
        "session_id": "backward-compat-004",
        "project_id": str(test_project_id),
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
    )

    # Assert
    assert response.status_code == 202
    response_data = response.json()
    # With AAP-60780, context_data is empty when no files are uploaded
    assert response_data[CONTEXT_KEY] == {}
    assert CONTEXT_KEY_FILE_IDS not in response_data[CONTEXT_KEY]


@pytest.mark.asyncio
async def test_all_existing_fields_present_in_response(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test that all existing response fields still present.

    Validates:
    - No breaking changes to response schema
    - All inherited fields present
    """
    # Arrange
    payload = {
        "prompt": "Full field test",
        "session_id": "backward-compat-005",
        "project_id": str(test_project_id),
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        json=payload,
    )

    # Assert
    assert response.status_code == 202
    data = response.json()

    # BaseResource fields
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "labels" in data

    # UserOwnedResource fields
    assert "created_by" in data
    assert "updated_by" in data

    # Invocation-specific fields
    assert "prompt" in data
    assert "session_id" in data
    assert "status" in data
    assert "started_at" in data
    assert "completed_at" in data
    assert CONTEXT_KEY in data
    assert "result" in data
    assert "error_message" in data
    assert "checkpoint_data" in data
