"""Unit tests for WorkflowService.get_publish_context."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.workflows.models.workflow_publish_event import PublishAction
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.fixture
def mock_service() -> WorkflowService:
    """Create a WorkflowService with mocked session."""
    session = AsyncMock()
    session.add = MagicMock()
    user = MagicMock()
    user.id = uuid4()
    service = WorkflowService.__new__(WorkflowService)
    service.session = session
    service.user = user
    return service


class TestGetPublishContext:
    """Tests for WorkflowService.get_publish_context."""

    @pytest.mark.asyncio
    async def test_empty_version_ids_returns_empty_set_and_dict(self, mock_service: WorkflowService) -> None:
        ever_published, timestamps = await mock_service.get_publish_context([])

        assert ever_published == set()
        assert timestamps == {}
        mock_service.session.exec.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_single_version_with_published_action(self, mock_service: WorkflowService) -> None:
        vid = uuid4()
        pub_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        mock_service.session.exec.return_value = [(vid, PublishAction.PUBLISHED, pub_time)]  # type: ignore[attr-defined]

        ever_published, timestamps = await mock_service.get_publish_context([vid])

        assert vid in ever_published
        assert vid in timestamps
        assert timestamps[vid].published_at == pub_time
        assert timestamps[vid].unpublished_at is None

    @pytest.mark.asyncio
    async def test_single_version_with_unpublished_action(self, mock_service: WorkflowService) -> None:
        vid = uuid4()
        unpub_time = datetime(2024, 7, 1, 8, 30, 0, tzinfo=UTC)
        mock_service.session.exec.return_value = [(vid, PublishAction.UNPUBLISHED, unpub_time)]  # type: ignore[attr-defined]

        ever_published, timestamps = await mock_service.get_publish_context([vid])

        assert vid not in ever_published
        assert vid in timestamps
        assert timestamps[vid].published_at is None
        assert timestamps[vid].unpublished_at == unpub_time

    @pytest.mark.asyncio
    async def test_single_version_with_both_published_and_unpublished(self, mock_service: WorkflowService) -> None:
        vid = uuid4()
        pub_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        unpub_time = datetime(2024, 6, 20, 9, 0, 0, tzinfo=UTC)
        mock_service.session.exec.return_value = [  # type: ignore[attr-defined]
            (vid, PublishAction.PUBLISHED, pub_time),
            (vid, PublishAction.UNPUBLISHED, unpub_time),
        ]

        ever_published, timestamps = await mock_service.get_publish_context([vid])

        assert vid in ever_published
        assert timestamps[vid].published_at == pub_time
        assert timestamps[vid].unpublished_at == unpub_time

    @pytest.mark.asyncio
    async def test_multiple_versions_with_mixed_actions(self, mock_service: WorkflowService) -> None:
        vid_a = uuid4()
        vid_b = uuid4()
        vid_c = uuid4()
        pub_time_a = datetime(2024, 1, 10, tzinfo=UTC)
        unpub_time_b = datetime(2024, 2, 15, tzinfo=UTC)
        pub_time_c = datetime(2024, 3, 20, tzinfo=UTC)
        unpub_time_c = datetime(2024, 4, 25, tzinfo=UTC)
        mock_service.session.exec.return_value = [  # type: ignore[attr-defined]
            (vid_a, PublishAction.PUBLISHED, pub_time_a),
            (vid_b, PublishAction.UNPUBLISHED, unpub_time_b),
            (vid_c, PublishAction.PUBLISHED, pub_time_c),
            (vid_c, PublishAction.UNPUBLISHED, unpub_time_c),
        ]

        ever_published, timestamps = await mock_service.get_publish_context([vid_a, vid_b, vid_c])

        assert vid_a in ever_published
        assert vid_b not in ever_published
        assert vid_c in ever_published

        assert timestamps[vid_a].published_at == pub_time_a
        assert timestamps[vid_a].unpublished_at is None

        assert timestamps[vid_b].published_at is None
        assert timestamps[vid_b].unpublished_at == unpub_time_b

        assert timestamps[vid_c].published_at == pub_time_c
        assert timestamps[vid_c].unpublished_at == unpub_time_c

    @pytest.mark.asyncio
    async def test_version_with_only_unpublished_not_in_ever_published(self, mock_service: WorkflowService) -> None:
        vid = uuid4()
        unpub_time = datetime(2024, 5, 5, 14, 0, 0, tzinfo=UTC)
        mock_service.session.exec.return_value = [(vid, PublishAction.UNPUBLISHED, unpub_time)]  # type: ignore[attr-defined]

        ever_published, timestamps = await mock_service.get_publish_context([vid])

        assert vid not in ever_published
        assert len(ever_published) == 0
        assert vid in timestamps
        assert timestamps[vid].unpublished_at == unpub_time
        assert timestamps[vid].published_at is None
