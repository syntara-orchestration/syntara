"""Integration tests for the full upload → conversion → agent execution pipeline.

Covers:
- Happy path: file converts, agent receives converted content in the LLM prompt
- Partial failure (FR-020): one file converts, one fails — invocation still completes

Note on FR-020 / partial context:
UploadedFileRetriever is fail-fast: if any ``file_ids`` entry is not CONVERTED,
retrieval raises and the planner continues with an empty document set. Assembler
then returns an empty ContextPackage payload (``{}``), so the LLM prompt is the
original user prompt with no ``--- CONTEXT ---`` block — not "use the converted
subset only".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from langchain_core.messages import HumanMessage

from syntara.core.constants import CONTEXT_KEY_FILE_IDS
from syntara.files.document_conversion.converters.pdf_converter import PDFConverter
from syntara.files.document_conversion.models.conversion_result import ConversionResult
from syntara.files.models import FileStatus
from tests.fixtures.files import get_fixtures_dir
from tests.integration.helpers.invocations import wait_for_invocation_execution

if TYPE_CHECKING:
    from httpx import AsyncClient

FIXTURES_DIR = get_fixtures_dir()
_METADATA_URL = "/api/v1/files/metadata"
# Unique line from tests/fixtures/files/sample.txt. Omit trailing "." — TextConverter
# escapes markdown specials (including ".") so converted content has "\." instead.
_SAMPLE_TXT_MARKER = "Line 1: This is a sample text file for testing file upload functionality"
# Text rendered from fixtures/sample.pdf when conversion succeeds
_SAMPLE_PDF_MARKER = "Sample PDF"


async def _files_metadata(client: AsyncClient, file_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch file metadata rows via the files metadata API."""
    # Wider value type satisfies httpx QueryParams stubs (list is invariant).
    params: list[tuple[str, str | int | float | bool | None]] = [("file_ids", fid) for fid in file_ids]
    response = await client.get(_METADATA_URL, params=params)
    assert response.status_code == 200, response.text
    files: list[dict[str, Any]] = response.json()["files"]
    return files


async def _statuses_by_filename(client: AsyncClient, file_ids: list[str]) -> dict[str, str]:
    """Map original filename → status for the given file_ids."""
    files = await _files_metadata(client, file_ids)
    assert len(files) == len(file_ids), f"Expected metadata for all file_ids, got {files!r}"
    return {f["filename"]: f["status"] for f in files}


def _llm_human_prompt(mock_openrouter_llm: MagicMock) -> str:
    """Return the first HumanMessage content sent to the mocked LLM."""
    bound_llm = mock_openrouter_llm.bind_tools.return_value
    bound_llm.ainvoke.assert_awaited()
    messages = bound_llm.ainvoke.call_args[0][0]
    human_messages = [m for m in messages if isinstance(m, HumanMessage)]
    assert human_messages, "Expected at least one HumanMessage in LLM call"
    content = human_messages[0].content
    assert isinstance(content, str)
    return content


async def _failing_pdf_convert(self: PDFConverter, file_content: bytes, file_metadata: object) -> ConversionResult:
    # Bound as an instance method via patch.object — ``self`` is required.
    return ConversionResult.failure_result(
        error_message="Injected PDF conversion failure for pipeline test",
        error_type="test_injected_failure",
        conversion_time_ms=1,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_relevancy_checker", "test_user_token_config")
async def test_upload_convert_execute_happy_path(
    auth_client_with_mocked_llm: AsyncClient,
    test_project_id: str,
    mock_openrouter_llm: MagicMock,
) -> None:
    """Upload a text file, convert it, and complete agent execution with file context."""
    text_path = FIXTURES_DIR / "sample.txt"
    assert text_path.exists()

    with text_path.open("rb") as text_file:
        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations/chat",
            data={
                "prompt": "Summarize the uploaded file.",
                "session_id": "pipeline-happy-path",
                "project_id": str(test_project_id),
            },
            files={"files": ("sample.txt", text_file, "text/plain")},
        )

    assert response.status_code == 202, response.text
    body = response.json()
    invocation_id = body["id"]
    file_ids = body["context_data"][CONTEXT_KEY_FILE_IDS]
    assert len(file_ids) == 1
    UUID(file_ids[0])

    async with wait_for_invocation_execution(
        auth_client_with_mocked_llm, invocation_id, max_wait_time=30.0
    ) as final_data:
        assert final_data is not None
        assert final_data["status"] == "completed"
        assert final_data["result"] is not None
        assert "Mock LLM response" in final_data["result"]["content"]
        assert final_data["context_data"][CONTEXT_KEY_FILE_IDS] == file_ids

    statuses = await _statuses_by_filename(auth_client_with_mocked_llm, file_ids)
    assert statuses == {"sample.txt": FileStatus.CONVERTED.value}

    # Agent received converted file content in the LLM prompt
    mock_openrouter_llm.bind_tools.assert_called()
    prompt_text = _llm_human_prompt(mock_openrouter_llm)
    assert "Summarize the uploaded file." in prompt_text
    assert "--- CONTEXT ---" in prompt_text
    assert "## documents" in prompt_text
    assert _SAMPLE_TXT_MARKER in prompt_text


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_relevancy_checker", "test_user_token_config")
async def test_partial_conversion_failure_invocation_still_completes(
    auth_client_with_mocked_llm: AsyncClient,
    test_project_id: str,
    mock_openrouter_llm: MagicMock,
) -> None:
    """One file converts, one fails — invocation proceeds (FR-020).

    With current fail-fast retrieval, a mixed CONVERTED + CONVERSION_FAILED set
    yields no uploaded-file documents in the LLM prompt, but execution still
    completes.

    Integration Temporal runs ``execute_internal_activity`` in-process, so
    patching ``PDFConverter.convert`` on this process applies to conversion.
    """
    text_path = FIXTURES_DIR / "sample.txt"
    pdf_path = FIXTURES_DIR / "sample.pdf"
    assert text_path.exists()
    assert pdf_path.exists()

    with (
        text_path.open("rb") as text_file,
        pdf_path.open("rb") as pdf_file,
        # In-process Temporal worker — patch must stay live through wait below.
        patch.object(PDFConverter, "convert", _failing_pdf_convert),
    ):
        files = [
            ("files", ("sample.txt", text_file, "text/plain")),
            ("files", ("sample.pdf", pdf_file, "application/pdf")),
        ]
        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations/chat",
            data={
                "prompt": "Use whatever file context is available.",
                "session_id": "pipeline-partial-failure",
                "project_id": str(test_project_id),
            },
            files=files,
        )

        assert response.status_code == 202, response.text
        body = response.json()
        invocation_id = body["id"]
        file_ids = body["context_data"][CONTEXT_KEY_FILE_IDS]
        assert len(file_ids) == 2

        # Keep the patch alive while Temporal runs conversion + execution
        async with wait_for_invocation_execution(
            auth_client_with_mocked_llm, invocation_id, max_wait_time=45.0
        ) as final_data:
            assert final_data is not None
            # FR-020: execution continues despite a conversion failure
            assert final_data["status"] == "completed"
            assert final_data["result"] is not None
            assert "Mock LLM response" in final_data["result"]["content"]
            assert set(final_data["context_data"][CONTEXT_KEY_FILE_IDS]) == set(file_ids)

    statuses = await _statuses_by_filename(auth_client_with_mocked_llm, file_ids)
    assert statuses["sample.txt"] == FileStatus.CONVERTED.value
    assert statuses["sample.pdf"] == FileStatus.CONVERSION_FAILED.value

    # Agent still ran; fail-fast retrieval → empty docs → Assembler returns
    # payload={} → orchestrator leaves the prompt unenhanced (no CONTEXT block).
    prompt_text = _llm_human_prompt(mock_openrouter_llm)
    assert "Use whatever file context is available." in prompt_text
    assert "--- CONTEXT ---" not in prompt_text
    assert "## documents" not in prompt_text
    assert _SAMPLE_TXT_MARKER not in prompt_text
    assert _SAMPLE_PDF_MARKER not in prompt_text
    assert "source_type" not in prompt_text
