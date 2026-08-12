"""Unit tests for scheduled trigger error handlers."""

import json
from unittest.mock import Mock

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import scheduled_trigger_not_found_handler, scheduled_trigger_sync_handler
from syntara.workflows.exceptions import ScheduledTriggerNotFoundError, ScheduledTriggerSyncError


class TestScheduledTriggerSyncHandler:
    """Test suite for scheduled_trigger_sync_handler."""

    def test_returns_503_with_problem_details(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/wf-123/versions/1/publish"

        exc = ScheduledTriggerSyncError("wf-123", 2)
        response = scheduled_trigger_sync_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 503
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["service_unavailable"]
        assert data["title"] == "Scheduled Trigger Sync Failed"
        assert data["code"] == "SCHEDULED_TRIGGER_SYNC_FAILED"
        assert data["retryable"] is True
        assert data["instance"] == "https://api.example.com/workflows/wf-123/versions/1/publish"


class TestScheduledTriggerNotFoundHandler:
    """Test suite for scheduled_trigger_not_found_handler."""

    def test_returns_404_with_problem_details(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/triggers/schedule-abc"

        exc = ScheduledTriggerNotFoundError("schedule-abc")
        response = scheduled_trigger_not_found_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Scheduled Trigger Not Found"
        assert data["code"] == "SCHEDULED_TRIGGER_NOT_FOUND"
        assert data["retryable"] is False
