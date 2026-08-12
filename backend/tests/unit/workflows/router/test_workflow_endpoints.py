"""Unit tests for workflow router endpoint functions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from syntara.workflows.models.workflow_version import PublishVersionRequest, WorkflowVersionRead
from syntara.workflows.router import (
    get_workflow,
    get_workflow_version,
    list_workflow_versions,
    list_workflows,
    publish_workflow_version,
    restore_workflow_version,
    update_workflow,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


async def _expect_http_exception(fn: Callable[..., Coroutine[Any, Any, Any]], **kwargs: object) -> HTTPException:
    """Call an async function and assert it raises HTTPException."""
    try:
        await fn(**kwargs)
    except HTTPException as exc:
        return exc
    pytest.fail(f"{fn.__name__} did not raise HTTPException")


class TestWorkflowEndpoints:
    """Tests for workflow router endpoint functions."""

    @pytest.mark.asyncio
    async def test_list_workflows_populates_published_version_numbers(self) -> None:
        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_result.resources = [MagicMock()]
        mock_service.list_workflows_cursor.return_value = mock_result
        mock_request = MagicMock()
        mock_request.query_params.items.return_value = []
        mock_params = MagicMock()
        mock_params.limit = 10
        mock_params.cursor = None
        mock_params.sort = None
        mock_params.include_total = False
        mock_visibility = MagicMock()
        mock_visibility.to_allowed_projects.return_value = None

        result = await list_workflows(
            request=mock_request,
            service=mock_service,
            params=mock_params,
            visibility=mock_visibility,
        )

        mock_service.list_workflows_cursor.assert_awaited_once_with(
            limit=10,
            cursor=None,
            sort=None,
            query_params_items=[],
            include_total=False,
            allowed_projects=None,
        )
        mock_service.populate_published_version_numbers.assert_awaited_once_with(mock_result.resources)
        assert result is mock_result

    @pytest.mark.asyncio
    async def test_get_workflow_calls_build_response(self) -> None:
        mock_service = AsyncMock()
        mock_workflow = MagicMock()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_service.get_workflow_with_version.return_value = (mock_workflow, mock_version)
        mock_response = MagicMock()
        workflow_id = uuid4()

        with patch(
            "syntara.workflows.router._build_workflow_with_version_response",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_build:
            result = await get_workflow(workflow_id=workflow_id, service=mock_service)

        mock_service.get_workflow_with_version.assert_awaited_once_with(workflow_id)
        mock_build.assert_awaited_once_with(mock_workflow, mock_version, mock_service)
        assert result is mock_response

    @pytest.mark.asyncio
    async def test_update_workflow_calls_build_response(self) -> None:
        mock_service = AsyncMock()
        mock_workflow = MagicMock()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_val_result = MagicMock()
        mock_service.update_workflow.return_value = (mock_workflow, mock_version, mock_val_result)
        mock_response = MagicMock()
        mock_request = MagicMock()
        mock_request.name = "updated"
        mock_request.description = None
        mock_request.labels = None
        mock_request.project_id = None
        mock_request.workflow_definition = None
        mock_request.change_description = None
        mock_request.expected_version = None
        workflow_id = uuid4()

        with patch(
            "syntara.workflows.router._build_workflow_with_version_response",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_build:
            result = await update_workflow(workflow_id=workflow_id, request=mock_request, service=mock_service)

        mock_build.assert_awaited_once_with(
            mock_workflow, mock_version, mock_service, validation_result=mock_val_result
        )
        assert result is mock_response

    @pytest.mark.asyncio
    async def test_list_workflow_versions_delegates_to_service(self) -> None:
        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_service.list_workflow_versions_cursor.return_value = mock_result
        mock_request = MagicMock()
        mock_request.query_params.items.return_value = []
        mock_params = MagicMock()
        mock_params.limit = 20
        mock_params.cursor = None
        mock_params.sort = None
        mock_params.include_total = True
        workflow_id = uuid4()

        result = await list_workflow_versions(
            workflow_id=workflow_id,
            request=mock_request,
            service=mock_service,
            params=mock_params,
        )

        mock_service.list_workflow_versions_cursor.assert_awaited_once_with(
            workflow_id=workflow_id,
            limit=20,
            cursor=None,
            sort=None,
            query_params_items=[],
            include_total=True,
        )
        assert result is mock_result

    @pytest.mark.asyncio
    async def test_get_workflow_version_calls_service_publish_context(self) -> None:
        workflow_id = uuid4()
        version_number = 3
        version_id = uuid4()
        published_version_id = uuid4()
        mock_service = AsyncMock()
        mock_workflow = MagicMock()
        mock_workflow.published_version_id = published_version_id
        mock_version = MagicMock()
        mock_version.id = version_id
        mock_workflow_result = MagicMock()
        mock_workflow_result.one_or_none.return_value = mock_workflow
        mock_version_result = MagicMock()
        mock_version_result.one_or_none.return_value = mock_version
        mock_service.session.exec.side_effect = [mock_workflow_result, mock_version_result]
        mock_deserialized = MagicMock()
        ever_published = {version_id}
        pub_ts = MagicMock()
        mock_service.get_publish_context.return_value = (ever_published, pub_ts)
        mock_validated = MagicMock()

        with (
            patch(
                "syntara.workflows.router.deserialize_workflow_version",
                return_value=mock_deserialized,
            ) as mock_deser,
            patch.object(
                WorkflowVersionRead,
                "model_validate",
                return_value=mock_validated,
            ) as mock_validate,
        ):
            result = await get_workflow_version(workflow_id=workflow_id, version=version_number, service=mock_service)

        mock_service.get_publish_context.assert_awaited_once_with([version_id])
        mock_deser.assert_called_once_with(mock_version, published_version_id, ever_published, pub_ts)
        mock_validate.assert_called_once_with(mock_deserialized)
        assert result is mock_validated

    @pytest.mark.asyncio
    async def test_get_workflow_version_raises_404_when_workflow_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_service.session.exec.return_value = mock_result

        exc = await _expect_http_exception(get_workflow_version, workflow_id=uuid4(), version=1, service=mock_service)
        assert exc.status_code == 404
        assert "Workflow not found" in str(exc.detail)

    @pytest.mark.asyncio
    async def test_get_workflow_version_raises_404_when_version_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_workflow = MagicMock()
        mock_workflow_result = MagicMock()
        mock_workflow_result.one_or_none.return_value = mock_workflow
        mock_version_result = MagicMock()
        mock_version_result.one_or_none.return_value = None
        mock_service.session.exec.side_effect = [mock_workflow_result, mock_version_result]

        exc = await _expect_http_exception(get_workflow_version, workflow_id=uuid4(), version=1, service=mock_service)
        assert exc.status_code == 404
        assert "Version 1 not found" in str(exc.detail)

    @pytest.mark.asyncio
    async def test_publish_workflow_version_calls_build_response(self) -> None:
        mock_service = AsyncMock()
        mock_workflow = MagicMock()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_service.publish_workflow_version.return_value = (mock_workflow, mock_version, "")
        mock_response = MagicMock()
        workflow_id = uuid4()
        request = PublishVersionRequest()

        with patch(
            "syntara.workflows.router._build_workflow_with_version_response",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_build:
            result = await publish_workflow_version(
                workflow_id=workflow_id,
                version=1,
                request=request,
                service=mock_service,
            )

        mock_service.publish_workflow_version.assert_awaited_once_with(
            workflow_id=workflow_id,
            version=1,
            name=None,
            change_description=None,
            workflow_definition=None,
            expected_version=None,
        )
        mock_build.assert_awaited_once_with(mock_workflow, mock_version, mock_service, warning="")
        assert result is mock_response

    @pytest.mark.asyncio
    async def test_restore_workflow_version_calls_build_response(self) -> None:
        """Verify restore_workflow_version delegates to build helper."""
        mock_service = AsyncMock()
        mock_workflow = MagicMock()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_service.restore_workflow_version.return_value = (mock_workflow, mock_version)
        mock_response = MagicMock()
        workflow_id = uuid4()

        with patch(
            "syntara.workflows.router._build_workflow_with_version_response",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_build:
            result = await restore_workflow_version(
                workflow_id=workflow_id,
                version=2,
                service=mock_service,
            )

        mock_service.restore_workflow_version.assert_awaited_once_with(
            workflow_id=workflow_id,
            version=2,
        )
        mock_build.assert_awaited_once_with(mock_workflow, mock_version, mock_service)
        assert result is mock_response
