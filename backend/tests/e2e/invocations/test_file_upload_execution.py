"""E2E test for the file-upload-to-agent-execution pipeline.

Verifies that uploading a file with an invocation triggers document
conversion, the executor waits for conversion to complete (AAP-61184),
and the invocation finishes successfully with converted files.

Requires a running backend with S3 and an LLM provider configured.
Run with: APP_BASE_URL=https://localhost:8000 uv run pytest tests/e2e/invocations/ -v
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

import httpx
import pytest
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context

pytestmark = [pytest.mark.e2e]

_POLL_INTERVAL = 0.5
_POLL_TIMEOUT = 60.0


def _poll_invocation(
    base_url: str,
    headers: dict[str, str],
    invocation_id: str,
) -> dict[str, Any]:
    """Poll until the invocation reaches a terminal status."""
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        resp = httpx.get(
            f"{base_url}/api/v1/invocations/{invocation_id}",
            headers=headers,
            verify=e2e_ssl_context(),
        )
        assert resp.status_code == 200
        data: dict[str, Any] = resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(_POLL_INTERVAL)
    pytest.fail(f"Invocation {invocation_id} did not complete within {_POLL_TIMEOUT}s")


class TestFileUploadExecution:
    """Verify the full file-upload → conversion → execution pipeline."""

    @pytest.mark.xfail(strict=False, reason="OpenRouter insufficient credits")
    def test_file_upload_invocation_completes_with_converted_files(
        self,
        syntara_base_url: str,
        auth_headers: dict[str, str],
        first_project_id: UUID,
        llm_credential_id: str,
        llm_model_id: str,
    ) -> None:
        """Upload a text file, verify invocation completes and files are converted."""
        file_content = b"The quick brown fox jumps over the lazy dog."
        files = [("files", ("test.txt", file_content, "text/plain"))]
        context_data = {
            "metadata": {
                "credential_id": llm_credential_id,
                "llm_model_id": llm_model_id,
            },
        }
        data = {
            "prompt": "Summarize the uploaded file.",
            "session_id": "e2e-file-upload-test",
            "project_id": str(first_project_id),
            "context_data": json.dumps(context_data),
        }

        response = httpx.post(
            f"{syntara_base_url}/api/v1/invocations/chat",
            data=data,
            files=files,
            headers=auth_headers,
            verify=e2e_ssl_context(),
        )
        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"

        invocation = response.json()
        invocation_id = invocation["id"]
        file_ids = invocation["context_data"]["file_ids"]
        assert len(file_ids) == 1
        UUID(file_ids[0])

        final = _poll_invocation(syntara_base_url, auth_headers, invocation_id)
        assert final["status"] == "completed", f"Invocation failed: {final.get('result')}"
        assert final["context_data"]["file_ids"] == file_ids

        file_ids_query = "&".join(f"file_ids={fid}" for fid in file_ids)
        meta_resp = httpx.get(
            f"{syntara_base_url}/api/v1/files/metadata?{file_ids_query}",
            headers=auth_headers,
            verify=e2e_ssl_context(),
        )
        assert meta_resp.status_code == 200
        files_meta = meta_resp.json()["files"]
        assert len(files_meta) == 1
        assert files_meta[0]["status"] == "converted"
