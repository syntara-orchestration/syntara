"""Contract tests for POST /invocations/chat with multipart/form-data file uploads.

These tests validate contract compliance with the OpenAPI schema:
- Multipart/form-data request schema with files array
- Files parameter is optional
- Files array maxItems: 10 constraint
- Response includes file_ids array in context_data (AAP-60780)
- FileMetadata is stored in database, not exposed in API response

Contract validates the POST /invocations/chat endpoint behavior.

NOTE: With AAP-60780 refactoring, context_data no longer contains file_metadata.
Instead, it contains file_ids (UUIDs) when files are uploaded.
"""

import uuid

import pytest
from httpx import AsyncClient

from syntara.core.constants import CONTEXT_KEY, CONTEXT_KEY_FILE_IDS


@pytest.mark.asyncio
async def test_files_parameter_is_optional(
    auth_client_with_mocked_llm: AsyncClient,
    test_project_id,
) -> None:
    """Test that files parameter is optional on POST /invocations/chat.

    Validates:
    - Multipart request without files succeeds
    - context_data is empty when no files uploaded (AAP-60780)
    """
    # Arrange
    data = {
        "prompt": "No files needed",
        "session_id": "contract-test-002",
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
    assert response_data.get(CONTEXT_KEY, {}) == {}
    assert CONTEXT_KEY_FILE_IDS not in response_data.get(CONTEXT_KEY, {})


@pytest.mark.asyncio
async def test_files_array_max_items_constraint(
    auth_client_with_mocked_llm: AsyncClient,
    test_project_id,
) -> None:
    """Test that POST /invocations/chat enforces maxItems: 10 constraint on files.

    Validates:
    - Accepts up to 10 files (202)
    - Rejects 11+ files (400)
    """
    # Arrange - 10 files (should succeed)
    files_10 = [("files", (f"file{i}.pdf", b"PDF content", "application/pdf")) for i in range(10)]
    data = {
        "prompt": "Process 10 files",
        "session_id": "contract-test-003",
        "project_id": str(test_project_id),
    }

    # Act - 10 files
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files_10,
    )

    # Assert - Should succeed (10 files is within the default limit)
    assert response.status_code == 202

    # Arrange - 11 files (should fail)
    files_11 = [("files", (f"file{i}.pdf", b"PDF content", "application/pdf")) for i in range(11)]

    # Act - 11 files
    response_11 = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files_11,
    )

    # Assert - Should reject
    assert response_11.status_code == 400


@pytest.mark.asyncio
async def test_response_schema_file_ids(
    auth_client_with_mocked_llm: AsyncClient,
    test_project_id,
) -> None:
    """Test file_ids array schema in POST /invocations/chat response.

    Validates:
    - file_ids is array in context_data (not file_metadata)
    - Each element is a valid UUID
    - Multiple files each get a unique file_id
    - FileMetadata is stored in database, not in API response (security)
    """
    # Arrange - Upload 2 files to validate array behavior
    files = [
        ("files", ("doc1.pdf", b"First document", "application/pdf")),
        ("files", ("doc2.txt", b"Second document", "text/plain")),
    ]
    data = {
        "prompt": "Upload test",
        "session_id": "contract-test-004",
        "project_id": str(test_project_id),
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert - Response structure
    assert response.status_code == 202
    response_data = response.json()
    assert CONTEXT_KEY in response_data
    assert CONTEXT_KEY_FILE_IDS in response_data[CONTEXT_KEY]

    file_ids = response_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]
    assert isinstance(file_ids, list)
    assert len(file_ids) == 2

    # Assert - Each file_id is a valid UUID
    for file_id in file_ids:
        uuid.UUID(file_id)  # Will raise if not valid UUID

    # Assert - All file_ids are unique
    assert len(file_ids) == len(set(file_ids)), "All file_ids should be unique"

    # SECURITY: Verify file_metadata is NOT exposed in API response
    # With AAP-60780, metadata lives in database, not in context_data
    assert "file_metadata" not in response_data[CONTEXT_KEY], "file_metadata should not be in API response"
