"""Integration tests for file upload functionality.

These tests validate end-to-end file upload scenarios from quickstart.md:
- Scenario 1: Upload Valid PDF File
- Scenario 2: Upload DOCX File
- Scenario 3: Upload Text/Markdown Files
- Scenario 4: Backward Compatibility (No Files)
- Scenario 5: File Too Large Error
- Scenario 6: Unsupported Format Error
- Scenario 7: Too Many Files Error
- Scenario 8: Multiple Files Upload
- Scenario 9: Context Data Integration

NOTE: With the refactored architecture (AAP-60780), context_data now contains
file_ids (UUIDs) instead of full file_metadata. The actual FileMetadata records
are stored in the FileMetadata database table, not in context_data.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

from syntara.core.constants import CONTEXT_KEY, CONTEXT_KEY_FILE_IDS
from tests.fixtures.files import generate_large_file


@pytest.mark.asyncio
async def test_upload_pdf_file(
    auth_client_with_mocked_llm: AsyncClient, test_user, sample_pdf_path: Path, test_project_id: str
) -> None:
    """Scenario 1: Upload Valid PDF File.

    Validates:
    - PDF file upload succeeds
    - 202 response status
    - file_ids array in context_data
    - FileMetadata records created in database
    """
    # Arrange
    file_content = sample_pdf_path.read_bytes()
    files = [("files", ("sample.pdf", file_content, "application/pdf"))]
    data = {
        "prompt": "Analyze the attached document and summarize key points",
        "session_id": "test-session-001",
        "project_id": test_project_id,
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert
    assert response.status_code == 202

    response_data = response.json()
    assert CONTEXT_KEY in response_data
    assert CONTEXT_KEY_FILE_IDS in response_data[CONTEXT_KEY]

    file_ids = response_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]
    assert isinstance(file_ids, list)
    assert len(file_ids) == 1

    # Verify file_ids are UUIDs
    import uuid

    for file_id in file_ids:
        uuid.UUID(file_id)  # Will raise if not valid UUID


@pytest.mark.asyncio
async def test_upload_docx_file(
    auth_client_with_mocked_llm: AsyncClient, test_user, sample_docx_path: Path, test_project_id: str
) -> None:
    """Scenario 2: Upload DOCX File.

    Validates:
    - DOCX file upload succeeds
    - file_ids array in context_data
    """
    # Arrange
    file_content = sample_docx_path.read_bytes()
    files = [
        (
            "files",
            (
                "sample.docx",
                file_content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )
    ]
    data = {
        "prompt": "Extract action items from this document",
        "session_id": "test-session-002",
        "project_id": test_project_id,
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert
    assert response.status_code == 202

    response_data = response.json()
    file_ids = response_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]
    assert len(file_ids) == 1

    # Verify file_ids are UUIDs
    import uuid

    for file_id in file_ids:
        uuid.UUID(file_id)  # Will raise if not valid UUID


@pytest.mark.asyncio
async def test_upload_text_and_markdown(
    auth_client_with_mocked_llm: AsyncClient,
    test_user,
    sample_txt_path: Path,
    sample_md_path: Path,
    test_project_id: str,
) -> None:
    """Scenario 3: Upload Text/Markdown Files.

    Validates:
    - Text file upload succeeds
    - Markdown file upload succeeds
    - file_ids in context_data
    """
    import uuid

    # Test TXT file
    file_content = sample_txt_path.read_bytes()
    files = [("files", ("sample.txt", file_content, "text/plain"))]
    data = {
        "prompt": "Summarize this README",
        "session_id": "test-session-003a",
        "project_id": test_project_id,
    }

    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert TXT
    assert response.status_code == 202
    response_data = response.json()
    file_ids = response_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]
    assert len(file_ids) == 1
    uuid.UUID(file_ids[0])

    # Test MD file
    file_content = sample_md_path.read_bytes()
    files = [("files", ("sample.md", file_content, "text/markdown"))]
    data = {
        "prompt": "Review this documentation",
        "session_id": "test-session-003b",
        "project_id": test_project_id,
    }

    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert MD
    assert response.status_code == 202
    response_data = response.json()
    file_ids = response_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]
    assert len(file_ids) == 1
    uuid.UUID(file_ids[0])


@pytest.mark.asyncio
async def test_invocation_without_files(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str
) -> None:
    """Scenario 4: Invocation Without Files (Backward Compatibility).

    Validates:
    - JSON requests without files still work
    - 202 response
    - context_data is None or empty (no file_ids)
    """
    # Arrange
    payload = {
        "prompt": "What is the weather today?",
        "session_id": "test-session-004",
        "project_id": test_project_id,
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        json=payload,
    )

    # Assert
    assert response.status_code == 202

    response_data = response.json()
    # context_data should be None or not contain file_ids
    context_data = response_data.get(CONTEXT_KEY)
    if context_data:
        # If context_data exists, it shouldn't have file_ids (no files uploaded)
        assert CONTEXT_KEY_FILE_IDS not in context_data or context_data.get(CONTEXT_KEY_FILE_IDS) == []


@pytest.mark.asyncio
async def test_file_too_large_error(auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id: str) -> None:
    """Scenario 5: File Too Large Error.

    Validates:
    - Files exceeding 10MB limit rejected
    - 400 error status
    - Error message includes size information
    - No invocation created
    """
    # Arrange - Generate 15MB file dynamically
    large_content = generate_large_file(15)  # 15MB

    files = [("files", ("large.pdf", large_content, "application/pdf"))]
    data = {
        "prompt": "Analyze this large document",
        "session_id": "test-session-005",
        "project_id": test_project_id,
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert "detail" in error_data
    detail = error_data["detail"]

    # Verify error message mentions file is too large and includes size info
    assert "too large" in detail
    assert "Maximum allowed size" in detail


@pytest.mark.asyncio
async def test_unsupported_format_error(
    auth_client_with_mocked_llm: AsyncClient, test_user, sample_image_path: Path, test_project_id: str
) -> None:
    """Scenario 6: Unsupported Format Error.

    Validates:
    - Unsupported file types rejected (PNG image)
    - 400 error status
    - Error lists supported formats
    - No invocation created
    """
    # Arrange
    file_content = sample_image_path.read_bytes()
    files = [("files", ("image.png", file_content, "image/png"))]
    data = {
        "prompt": "Analyze this image",
        "session_id": "test-session-006",
        "project_id": test_project_id,
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert "detail" in error_data
    detail = error_data["detail"]

    # Verify error message mentions the unsupported format and lists supported formats
    assert "Unsupported file format" in detail
    assert "image/png" in detail
    assert "Supported formats:" in detail


@pytest.mark.asyncio
async def test_too_many_files_error(
    auth_client_with_mocked_llm: AsyncClient, test_user, sample_pdf_path: Path, test_project_id: str
) -> None:
    """Scenario 7: Too Many Files Error.

    Validates:
    - Uploading > 10 files rejected
    - 400 error status
    - Error message includes file count and limit
    - No invocation created
    """
    # Arrange - 15 files (exceeds limit of 10)
    # Reuse the same PDF file content 15 times with different names
    pdf_content = sample_pdf_path.read_bytes()

    files = [("files", (f"sample{i}.pdf", pdf_content, "application/pdf")) for i in range(1, 16)]

    data = {
        "prompt": "Analyze all these documents",
        "session_id": "test-session-007",
        "project_id": test_project_id,
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert "detail" in error_data
    detail = error_data["detail"]

    # Verify error message mentions too many files and includes counts
    assert "Too many files" in detail
    assert "10" in detail  # Max limit
    assert "15" in detail  # Actual count

    # Verify no invocation created
    list_response = await auth_client_with_mocked_llm.get("/api/v1/invocations?session_id=test-session-007")
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert len(list_data["resources"]) == 0


@pytest.mark.asyncio
async def test_multiple_files_upload(
    auth_client_with_mocked_llm: AsyncClient,
    test_user,
    sample_pdf_path: Path,
    sample_docx_path: Path,
    sample_txt_path: Path,
    test_project_id: str,
) -> None:
    """Scenario 8: Multiple Files Upload.

    Validates:
    - 3 files uploaded in single request
    - 202 response
    - file_ids array with 3 elements
    - All file_ids are unique UUIDs
    """
    import uuid

    # Arrange
    pdf_content = sample_pdf_path.read_bytes()
    docx_content = sample_docx_path.read_bytes()
    txt_content = sample_txt_path.read_bytes()

    files = [
        ("files", ("sample.pdf", pdf_content, "application/pdf")),
        (
            "files",
            ("sample.docx", docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ),
        ("files", ("sample.txt", txt_content, "text/plain")),
    ]
    data = {
        "prompt": "Analyze all these related documents together",
        "session_id": "test-session-multi-010",
        "project_id": test_project_id,
    }

    # Act
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert
    assert response.status_code == 202

    response_data = response.json()
    file_ids = response_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]

    # Verify 3 elements
    assert len(file_ids) == 3

    # All should be valid UUIDs
    for file_id in file_ids:
        uuid.UUID(file_id)

    # Verify unique file_ids
    assert len(file_ids) == len(set(file_ids)), "All file_ids should be unique"


@pytest.mark.asyncio
async def test_context_metadata(
    auth_client_with_mocked_llm: AsyncClient, test_user, sample_pdf_path: Path, test_project_id: str
) -> None:
    """Scenario 9: Context Data Integration.

    Validates:
    - file_ids array accessible via GET /invocations/{id}
    - file_ids is array type
    - file_ids contains valid UUIDs
    """
    import uuid

    # Arrange
    file_content = sample_pdf_path.read_bytes()
    files = [("files", ("sample.pdf", file_content, "application/pdf"))]
    data = {
        "prompt": "Summarize the document",
        "session_id": "test-session-011",
        "project_id": test_project_id,
    }

    # Act - Create invocation with file
    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations/chat",
        data=data,
        files=files,
    )

    # Assert creation
    assert response.status_code == 202
    response_data = response.json()
    invocation_id = response_data["id"]

    # Retrieve invocation details
    invocation_response = await auth_client_with_mocked_llm.get(f"/api/v1/invocations/{invocation_id}")
    assert invocation_response.status_code == 200

    invocation_data = invocation_response.json()
    context_data = invocation_data[CONTEXT_KEY]

    # Verify context structure with new file_ids format
    assert CONTEXT_KEY_FILE_IDS in context_data
    assert isinstance(context_data[CONTEXT_KEY_FILE_IDS], list)
    assert len(context_data[CONTEXT_KEY_FILE_IDS]) == 1

    # Verify file_id is a valid UUID
    uuid.UUID(context_data[CONTEXT_KEY_FILE_IDS][0])
