"""Integration tests for document conversion with agent invocation workflow.

NOTE: With the refactored architecture (AAP-60780), context_data now contains
file_ids (UUIDs) instead of full file_metadata. The actual FileMetadata records
are stored in the FileMetadata database table, not in context_data.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from syntara.core.constants import CONTEXT_KEY_FILE_IDS
from tests.fixtures.files import get_fixtures_dir
from tests.integration.helpers.invocations import wait_for_invocation_execution

FIXTURES_DIR = get_fixtures_dir()


@pytest.mark.asyncio
async def test_invoke_agent_with_pdf_document_conversion(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test complete agent invocation workflow with PDF document conversion.

    This test demonstrates T028 requirements:
    - Creation of an Invocation using POST with documents included
    - Document conversion processing in background task
    - Invocation execution after conversion completes

    With AAP-60780 changes:
    - context_data contains file_ids (UUIDs) instead of file_metadata
    - FileMetadata records are stored in the database

    """
    # Load test PDF file
    pdf_file_path = FIXTURES_DIR / "sample.pdf"
    assert pdf_file_path.exists(), f"Test PDF file not found at {pdf_file_path}"

    # Create multipart form data with two document uploads (same filename)
    with pdf_file_path.open("rb") as pdf_file:
        files = [
            ("files", ("sample.pdf", pdf_file, "application/pdf")),
            ("files", ("sample.pdf", pdf_file, "application/pdf")),
        ]
        data = {
            "prompt": "Please analyze the content of the uploaded documents and summarize them.",
            "session_id": "document-conversion-test",
            "project_id": str(test_project_id),
        }

        # POST invocation with document
        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations/chat",
            data=data,
            files=files,
        )

        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
        invocation_data = response.json()
        invocation_id = invocation_data["id"]

        # Verify invocation created with expected structure
        assert "id" in invocation_data
        assert invocation_data["status"] == "created"
        assert invocation_data["prompt"] == "Please analyze the content of the uploaded documents and summarize them."
        assert invocation_data["session_id"] == "document-conversion-test"
        assert invocation_data["created_by"] == str(test_user.id)

        # Verify context_data contains file_ids (new architecture)
        assert "context_data" in invocation_data
        assert invocation_data["context_data"] is not None
        assert CONTEXT_KEY_FILE_IDS in invocation_data["context_data"]

        file_ids = invocation_data["context_data"][CONTEXT_KEY_FILE_IDS]
        assert isinstance(file_ids, list)
        assert len(file_ids) == 2

        # Verify all file_ids are valid UUIDs
        for file_id in file_ids:
            UUID(file_id)  # Will raise if not valid UUID

        # Wait for background document conversion and invocation execution
        async with wait_for_invocation_execution(
            auth_client_with_mocked_llm, invocation_id, max_wait_time=15.0
        ) as final_data:
            # Verify execution completed
            assert final_data is not None
            assert final_data["status"] == "completed"

            # Verify the result contains converted content
            assert final_data["status"] == "completed"
            assert final_data["result"] is not None
            assert "content" in final_data["result"]
            result_content = final_data["result"]["content"]
            assert "Mock LLM response" in result_content

            # Verify file_ids are still present in context_data
            assert CONTEXT_KEY_FILE_IDS in final_data["context_data"]
            final_file_ids = final_data["context_data"][CONTEXT_KEY_FILE_IDS]
            assert len(final_file_ids) == 2


@pytest.mark.asyncio
async def test_invoke_agent_with_text_document_conversion(
    auth_client_with_mocked_llm: AsyncClient, test_user, test_project_id
) -> None:
    """Test agent invocation workflow with text file document conversion.

    Tests text-to-markdown conversion workflow.
    """
    # Load test text file
    text_file_path = FIXTURES_DIR / "sample.txt"
    assert text_file_path.exists(), f"Test text file not found at {text_file_path}"

    # Create multipart form data with document upload
    with text_file_path.open("rb") as text_file:
        files = {"files": ("sample.txt", text_file, "text/plain")}
        data = {
            "prompt": "What is the main content of this text file?",
            "session_id": "text-conversion-test",
            "project_id": str(test_project_id),
        }

        # POST invocation with document
        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations/chat",
            data=data,
            files=files,
        )

        assert response.status_code == 202
        invocation_data = response.json()
        invocation_id = invocation_data["id"]

        # Verify invocation created with file_ids (new architecture)
        file_ids = invocation_data["context_data"][CONTEXT_KEY_FILE_IDS]
        assert len(file_ids) == 1

        # Verify file_id is a valid UUID
        UUID(file_ids[0])

        # Wait for conversion and execution
        async with wait_for_invocation_execution(
            auth_client_with_mocked_llm, invocation_id, max_wait_time=10.0
        ) as final_data:
            # Verify execution completed
            assert final_data is not None
            assert final_data["status"] == "completed"

            # Verify the result contains converted content
            assert final_data["status"] == "completed"
            assert final_data["result"] is not None
            assert "content" in final_data["result"]
            result_content = final_data["result"]["content"]
            assert "Mock LLM response" in result_content

            # Verify file_ids are still present in context_data
            assert CONTEXT_KEY_FILE_IDS in final_data["context_data"]
            final_file_ids = final_data["context_data"][CONTEXT_KEY_FILE_IDS]
            assert len(final_file_ids) == 1
