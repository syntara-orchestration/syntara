"""Integration test for RetrieverService with agent invocation workflow."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_invocation_with_invalid_file_id_fails_gracefully(
    auth_client_with_mocked_llm, test_user, test_project_id
) -> None:
    """Test that invoking with an invalid file_id fails gracefully."""
    response = await auth_client_with_mocked_llm.post(
        "/_internal/invocations",
        json={
            "prompt": "Process this file",
            "session_id": f"invalid-file-test-{uuid4().hex[:8]}",
            "project_id": str(test_project_id),
            "context_data": {"file_ids": ["00000000-0000-0000-0000-000000000000"]},
        },
    )

    assert response.status_code == 422, f"Expected 422 for invalid file_id, got {response.status_code}"

    error_data = response.json()
    assert "detail" in error_data or "title" in error_data
