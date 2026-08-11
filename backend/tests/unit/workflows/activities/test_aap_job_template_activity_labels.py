"""Unit tests for AAP label resolution in job template activity.

Tests label name → ID resolution including:
- Resolving existing labels by name
- Creating new labels when they don't exist
- Organization filtering for labels
- Error handling for label resolution failures
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from syntara.workflows.workflow_engine.activities.aap_common import resolve_label_ids
from syntara.workflows.workflow_engine.activities.aap_job_template_activity import AAPJobExecutionError

TEST_AAP_URL = "http://test.aap"
TEST_ORG_NAME = "Engineering"
TEST_ORG_ID = 5


def create_http_response(
    status_code: int, json: dict[str, object] | None = None, text: str | None = None
) -> httpx.Response:
    """Helper to create mock HTTP responses."""
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", TEST_AAP_URL),
        json=json,
        text=text,
    )


@pytest.mark.asyncio
class TestLabelResolution:
    """Tests for resolve_label_ids function."""

    async def test_resolve_existing_labels(self) -> None:
        """Should resolve existing label names to IDs within organization."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock organization lookup
        org_response = create_http_response(200, {"results": [{"id": TEST_ORG_ID, "name": TEST_ORG_NAME}]})

        # Mock label lookups - both labels exist in the organization
        label1_response = create_http_response(
            200,
            {
                "results": [
                    {"id": 10, "name": "dev", "organization": TEST_ORG_ID},
                    {"id": 99, "name": "dev", "organization": 999},  # Different org - should be filtered
                ]
            },
        )
        label2_response = create_http_response(
            200, {"results": [{"id": 20, "name": "production", "organization": TEST_ORG_ID}]}
        )

        client.get.side_effect = [org_response, label1_response, label2_response]

        label_ids = await resolve_label_ids(
            client,
            ["dev", "production"],
            organization_name=TEST_ORG_NAME,
            organization_id=None,
            auth_headers={},
            basic_auth=None,
            base_url=TEST_AAP_URL,
            error_class=AAPJobExecutionError,
        )

        assert label_ids == [10, 20]
        assert client.get.call_count == 3  # 1 org + 2 labels

        # Verify organization lookup
        org_call = client.get.call_args_list[0]
        assert org_call.kwargs["params"] == {"name": TEST_ORG_NAME}

        # Verify label lookups
        label1_call = client.get.call_args_list[1]
        assert label1_call.kwargs["params"] == {"name": "dev", "page_size": "200"}

        label2_call = client.get.call_args_list[2]
        assert label2_call.kwargs["params"] == {"name": "production", "page_size": "200"}

    async def test_create_new_label_when_not_exists(self) -> None:
        """Should create new label when it doesn't exist in organization."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock organization lookup
        org_response = create_http_response(200, {"results": [{"id": TEST_ORG_ID, "name": TEST_ORG_NAME}]})

        # Mock label lookup - label doesn't exist
        label_lookup_response = create_http_response(
            200,
            {"results": []},  # No results - label doesn't exist
        )

        # Mock label creation
        label_create_response = create_http_response(201, {"id": 30, "name": "staging", "organization": TEST_ORG_ID})

        client.get.side_effect = [org_response, label_lookup_response]
        client.post.return_value = label_create_response

        label_ids = await resolve_label_ids(
            client,
            ["staging"],
            organization_name=TEST_ORG_NAME,
            organization_id=None,
            auth_headers={},
            basic_auth=None,
            base_url=TEST_AAP_URL,
            error_class=AAPJobExecutionError,
        )

        assert label_ids == [30]

        # Verify label was created with correct body
        create_call = client.post.call_args
        assert create_call.kwargs["json"] == {
            "name": "staging",
            "organization": TEST_ORG_ID,
        }

    async def test_create_label_when_exists_in_different_org(self) -> None:
        """Should create new label when it exists but in a different organization."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock organization lookup
        org_response = create_http_response(200, {"results": [{"id": TEST_ORG_ID, "name": TEST_ORG_NAME}]})

        # Mock label lookup - label exists but in different organization
        label_lookup_response = create_http_response(
            200,
            {
                "results": [
                    {"id": 99, "name": "dev", "organization": 999},  # Different org
                ]
            },
        )

        # Mock label creation
        label_create_response = create_http_response(201, {"id": 40, "name": "dev", "organization": TEST_ORG_ID})

        client.get.side_effect = [org_response, label_lookup_response]
        client.post.return_value = label_create_response

        label_ids = await resolve_label_ids(
            client,
            ["dev"],
            organization_name=TEST_ORG_NAME,
            organization_id=None,
            auth_headers={},
            basic_auth=None,
            base_url=TEST_AAP_URL,
            error_class=AAPJobExecutionError,
        )

        assert label_ids == [40]
        assert client.post.call_count == 1  # Label was created

    async def test_error_when_organization_not_found(self) -> None:
        """Should raise error when organization doesn't exist."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock organization lookup - not found
        org_response = create_http_response(200, {"results": []})
        client.get.return_value = org_response

        with pytest.raises(AAPJobExecutionError, match="Organization 'NonExistent' not found"):
            await resolve_label_ids(
                client,
                ["dev"],
                organization_name="NonExistent",
                organization_id=None,
                auth_headers={},
                basic_auth=None,
                base_url=TEST_AAP_URL,
                error_class=AAPJobExecutionError,
            )

    async def test_error_on_label_lookup_failure(self) -> None:
        """Should raise error when label lookup fails."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock organization lookup
        org_response = create_http_response(200, {"results": [{"id": TEST_ORG_ID, "name": TEST_ORG_NAME}]})

        # Mock label lookup failure
        label_error = httpx.HTTPStatusError(
            "404 Not Found",
            request=httpx.Request("GET", TEST_AAP_URL),
            response=create_http_response(404, text="Not found"),
        )
        client.get.side_effect = [org_response, label_error]

        with pytest.raises(AAPJobExecutionError, match="Failed to resolve/create label 'dev'"):
            await resolve_label_ids(
                client,
                ["dev"],
                organization_name=TEST_ORG_NAME,
                organization_id=None,
                auth_headers={},
                basic_auth=None,
                base_url=TEST_AAP_URL,
                error_class=AAPJobExecutionError,
            )

    async def test_error_on_label_creation_failure(self) -> None:
        """Should raise error when label creation fails."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock organization lookup
        org_response = create_http_response(200, {"results": [{"id": TEST_ORG_ID, "name": TEST_ORG_NAME}]})

        # Mock label lookup - label doesn't exist
        label_lookup_response = create_http_response(200, {"results": []})

        # Mock label creation failure
        create_error = httpx.HTTPStatusError(
            "403 Forbidden",
            request=httpx.Request("POST", TEST_AAP_URL),
            response=create_http_response(403, text="Permission denied"),
        )

        client.get.side_effect = [org_response, label_lookup_response]
        client.post.side_effect = create_error

        with pytest.raises(AAPJobExecutionError, match="Failed to resolve/create label 'staging'"):
            await resolve_label_ids(
                client,
                ["staging"],
                organization_name=TEST_ORG_NAME,
                organization_id=None,
                auth_headers={},
                basic_auth=None,
                base_url=TEST_AAP_URL,
                error_class=AAPJobExecutionError,
            )

    async def test_resolve_multiple_labels_mixed_scenarios(self) -> None:
        """Should handle mix of existing and new labels."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock organization lookup
        org_response = create_http_response(200, {"results": [{"id": TEST_ORG_ID, "name": TEST_ORG_NAME}]})

        # Mock first label exists
        label1_response = create_http_response(
            200, {"results": [{"id": 10, "name": "dev", "organization": TEST_ORG_ID}]}
        )

        # Mock second label doesn't exist
        label2_response = create_http_response(200, {"results": []})
        label2_create_response = create_http_response(201, {"id": 50, "name": "new-label", "organization": TEST_ORG_ID})

        # Mock third label exists
        label3_response = create_http_response(
            200, {"results": [{"id": 20, "name": "production", "organization": TEST_ORG_ID}]}
        )

        client.get.side_effect = [org_response, label1_response, label2_response, label3_response]
        client.post.return_value = label2_create_response

        label_ids = await resolve_label_ids(
            client,
            ["dev", "new-label", "production"],
            organization_name=TEST_ORG_NAME,
            organization_id=None,
            auth_headers={},
            basic_auth=None,
            base_url=TEST_AAP_URL,
            error_class=AAPJobExecutionError,
        )

        assert label_ids == [10, 50, 20]
        assert client.get.call_count == 4  # 1 org + 3 labels
        assert client.post.call_count == 1  # Only second label created

    async def test_passes_auth_headers_and_basic_auth(self) -> None:
        """Should pass authentication headers and basic auth to HTTP requests."""
        client = AsyncMock(spec=httpx.AsyncClient)
        auth_headers = {"Authorization": "Bearer token123"}
        basic_auth = httpx.BasicAuth("user", "pass")

        # Mock organization lookup
        org_response = create_http_response(200, {"results": [{"id": TEST_ORG_ID, "name": TEST_ORG_NAME}]})

        # Mock label lookup
        label_response = create_http_response(
            200, {"results": [{"id": 10, "name": "dev", "organization": TEST_ORG_ID}]}
        )

        client.get.side_effect = [org_response, label_response]

        await resolve_label_ids(
            client,
            ["dev"],
            organization_name=TEST_ORG_NAME,
            organization_id=None,
            auth_headers=auth_headers,
            basic_auth=basic_auth,
            base_url=TEST_AAP_URL,
            error_class=AAPJobExecutionError,
        )

        # Verify all requests included auth
        for call in client.get.call_args_list:
            assert call.kwargs["headers"] == auth_headers
            assert call.kwargs["auth"] == basic_auth

    async def test_handles_409_conflict_with_retry(self) -> None:
        """Should handle 409 Conflict by re-querying for the concurrently created label."""
        client = AsyncMock(spec=httpx.AsyncClient)

        # Mock responses: label doesn't exist initially, creation returns 409, then label exists on retry
        label_not_found_response = create_http_response(200, {"results": []})
        conflict_response = create_http_response(409, text="Conflict: Label already exists")
        label_found_response = create_http_response(
            200, {"results": [{"id": 42, "name": "concurrent-label", "organization": TEST_ORG_ID}]}
        )

        # First GET returns empty, POST returns 409, second GET returns the label
        client.get.side_effect = [label_not_found_response, label_found_response]
        client.post.return_value = conflict_response

        label_ids = await resolve_label_ids(
            client,
            ["concurrent-label"],
            organization_name=None,
            organization_id=TEST_ORG_ID,
            auth_headers={},
            basic_auth=None,
            base_url=TEST_AAP_URL,
            error_class=AAPJobExecutionError,
        )

        assert label_ids == [42]
        assert client.get.call_count == 2  # Initial lookup + retry after 409
        assert client.post.call_count == 1  # Attempted creation that got 409
