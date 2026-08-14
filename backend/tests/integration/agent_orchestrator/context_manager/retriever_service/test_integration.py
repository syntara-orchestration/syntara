"""Integration test for RetrieverService with agent invocation workflow."""

import asyncio
from uuid import UUID, uuid4

import pytest

from syntara.agent_orchestrator.models import Invocation
from syntara.agent_orchestrator.services.streaming_service import get_invocation_stream_id
from syntara.core.cache.stream import StreamClient
from syntara.core.constants import CONTEXT_KEY, CONTEXT_KEY_FILE_IDS
from syntara.files.models import FileMetadata
from tests.fixtures.files import get_fixtures_dir
from tests.integration.helpers.invocations import wait_for_invocation_execution

pytestmark = pytest.mark.integration

FIXTURES_DIR = get_fixtures_dir()


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_relevancy_checker", "test_user_token_config")
async def test_retriever_service_integration_with_agent_invocation(
    auth_client_with_mocked_llm, test_user, mock_openrouter_llm, test_project_id
) -> None:
    """Test complete file upload -> invocation -> agent execution flow.

    1. File uploaded via invocations API
    2. File IDs returned in context_data
    3. Invocation executes and completes successfully
    4. Agent LLM is invoked with the prompt
    """
    text_file_path = FIXTURES_DIR / "sample.txt"
    assert text_file_path.exists(), f"Test text file not found at {text_file_path}"

    with text_file_path.open("rb") as text_file:
        files = {"files": ("machine_learning_guide.txt", text_file, "text/plain")}
        data = {
            "prompt": "What are the key machine learning algorithms I should know about?",
            "session_id": f"retriever-integration-test-{uuid4().hex[:8]}",
            "project_id": str(test_project_id),
        }

        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations/chat",
            data=data,
            files=files,
        )

    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
    invocation_data = response.json()
    assert "id" in invocation_data
    invocation_id = invocation_data["id"]

    assert CONTEXT_KEY in invocation_data
    assert CONTEXT_KEY_FILE_IDS in invocation_data[CONTEXT_KEY]
    file_ids = invocation_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]
    assert len(file_ids) == 1

    async with wait_for_invocation_execution(
        auth_client_with_mocked_llm, invocation_id, max_wait_time=30.0
    ) as final_data:
        assert final_data is not None
        assert final_data["status"] == "completed"

        bound_llm = mock_openrouter_llm.bind_tools.return_value
        bound_llm.ainvoke.assert_called()
        agent_call_args = bound_llm.ainvoke.call_args[0][0]
        messages_str = str(agent_call_args)
        assert "What are the key machine learning algorithms I should know about?" in messages_str


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_relevancy_checker", "test_user_token_config")
async def test_file_upload_with_streaming_events(
    auth_client_with_mocked_llm, test_user, mock_openrouter_llm, test_project_id
) -> None:
    """Test complete flow: upload files -> execute -> response streams via Redis.

    Verifies that file upload invocations produce streaming events
    that can be consumed via WebSocket.

    Flow tested:
    1. Upload file via invocations API
    2. Invocation executes with file context
    3. Streaming events (delta, completion) are published to Redis
    4. Events can be read back from the stream
    """
    text_file_path = FIXTURES_DIR / "sample.txt"
    assert text_file_path.exists()

    with text_file_path.open("rb") as text_file:
        files = {"files": ("test_document.txt", text_file, "text/plain")}
        data = {
            "prompt": "Summarize this document",
            "session_id": f"streaming-integration-test-{uuid4().hex[:8]}",
            "project_id": str(test_project_id),
        }

        response = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations/chat",
            data=data,
            files=files,
        )

        assert response.status_code == 202
        invocation_data = response.json()
        invocation_id = invocation_data["id"]

        async with wait_for_invocation_execution(
            auth_client_with_mocked_llm, invocation_id, max_wait_time=30.0
        ) as final_data:
            assert final_data is not None
            assert final_data["status"] == "completed"

            stream_id = get_invocation_stream_id(UUID(invocation_id))

            async with StreamClient() as client:
                info = await client.info(stream_id)

                assert info["exists"] is True, "Invocation stream should exist in Redis"
                assert info["length"] > 0, "Stream should contain events"

                events: list[dict[str, object]] = []
                try:
                    async with asyncio.timeout(10.0):
                        async for event in client.events(stream_id, start_id="0-0"):
                            events.append(event)
                            if event.get("event_type") == "completion":
                                break
                except TimeoutError:
                    pytest.fail(
                        f"Timed out waiting for completion event. "
                        f"Received {len(events)} events: {[e.get('event_type') for e in events]}"
                    )

                event_types = [e.get("event_type") for e in events]
                assert "completion" in event_types, f"Expected 'completion' event in stream. Got: {event_types}"

                completion_event = next(e for e in events if e.get("event_type") == "completion")
                assert completion_event["invocation_id"] == invocation_id
                assert "timestamp" in completion_event


@pytest.mark.asyncio
async def test_invocation_with_invalid_file_id_fails_gracefully(
    auth_client_with_mocked_llm, test_user, test_project_id
) -> None:
    """Test that invoking with an invalid file_id fails gracefully.

    Verifies graceful error handling when file_id doesn't exist.
    """
    data = {
        "prompt": "Process this file",
        "session_id": f"invalid-file-test-{uuid4().hex[:8]}",
        "project_id": str(test_project_id),
        "context_data": '{"file_ids": ["00000000-0000-0000-0000-000000000000"]}',
    }

    response = await auth_client_with_mocked_llm.post(
        "/api/v1/invocations",
        data=data,
    )

    assert response.status_code == 422, f"Expected 422 for invalid file_id, got {response.status_code}"

    error_data = response.json()
    assert "detail" in error_data or "title" in error_data, "Error response should follow RFC 9457 format"


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_relevancy_checker")
async def test_file_upload_creates_db_records(
    auth_client_with_mocked_llm, test_user, test_db_session, test_project_id
) -> None:
    """Verify file upload creates FileMetadata records in the database."""
    text_file_path = FIXTURES_DIR / "sample.txt"
    assert text_file_path.exists()

    with text_file_path.open("rb") as text_file:
        files = {"files": ("test_file.txt", text_file, "text/plain")}
        data = {
            "prompt": "Test prompt",
            "session_id": f"db-record-test-{uuid4().hex[:8]}",
            "project_id": str(test_project_id),
        }

        response = await auth_client_with_mocked_llm.post("/api/v1/invocations/chat", data=data, files=files)

        assert response.status_code == 202
        invocation_data = response.json()

        file_ids = invocation_data[CONTEXT_KEY][CONTEXT_KEY_FILE_IDS]
        assert len(file_ids) == 1

        file_metadata = await test_db_session.get(FileMetadata, UUID(file_ids[0]))

        assert file_metadata is not None
        assert file_metadata.filename == "test_file.txt"
        assert file_metadata.mime_type == "text/plain"
        assert file_metadata.size_bytes > 0
        assert file_metadata.file_path is not None


@pytest.mark.asyncio
async def test_callback_url_stripped_from_external_context_data(
    auth_client_with_mocked_llm, test_user, test_db_session, test_project_id
) -> None:
    """Verify callback_url in context_data is stripped for non-cert-authenticated requests.

    External callers must not be able to inject callback_url — the SSRF mitigation
    in the router strips internal-only fields before persisting.
    """
    callback_url = "http://example.com/executions/123/activities/456/signal"
    data = {
        "prompt": "Test prompt",
        "session_id": f"callback-test-{uuid4().hex[:8]}",
        "project_id": str(test_project_id),
        "context_data": f'{{"callback_url": "{callback_url}", "agent": "my-agent"}}',
    }

    response = await auth_client_with_mocked_llm.post("/api/v1/invocations/chat", data=data)
    assert response.status_code == 202

    invocation_id = response.json()["id"]
    invocation = await test_db_session.get(Invocation, UUID(invocation_id))
    assert invocation is not None
    assert invocation.context_data is not None
    assert invocation.context_data.get("callback_url") is None
    assert invocation.context_data.get("agent") == "my-agent"
