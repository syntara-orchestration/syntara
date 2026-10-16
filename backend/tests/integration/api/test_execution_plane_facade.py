"""Integration tests for the AO Execution Plane facade pagination contract.

EP only supports ``limit`` and returns a bare JSON array; cursor, sort, and
include_total are accepted by the AO query model (consistent with BaseListParams)
but only ``limit`` is forwarded to EP.

EP HTTP calls are intercepted by respx; the AO database (postgres) is real.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
import respx
from httpx import AsyncClient, Response

from syntara.execution_plane import client as ep_client_module

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from contextlib import AbstractContextManager

_EP_BASE = "https://ep.test"

_TARGET_1: dict[str, Any] = {
    "id": "7beaf7e4-0000-4000-8000-000000000001",
    "cluster_id": "7beaf7e4-0000-4000-8000-000000000002",
    "name": "workers-1",
    "backend_type": "vanilla_k8s",
    "endpoint": "https://cluster.example",
    "placement": {
        "type": "kubernetes",
        "namespace": "ep-workers",
        "node_selectors": [],
        "tolerations": [],
    },
    "status": "active",
    "enabled": True,
    "is_default": True,
    "labels": {},
    "created_at": "2026-10-01T00:00:00Z",
}

_TARGET_2: dict[str, Any] = {
    **_TARGET_1,
    "id": "7beaf7e4-0000-4000-8000-000000000003",
    "name": "workers-2",
    "created_at": "2026-10-02T00:00:00Z",
}

_WORK_ITEM_1: dict[str, Any] = {
    "id": "aaaaaaaa-0000-4000-8000-000000000001",
    "status": "completed",
    "result": None,
    "created_at": "2026-10-01T00:00:00Z",
    "claimed_at": None,
    "completed_at": None,
}


@pytest.fixture(autouse=True)
def _ep_settings(override_settings: Callable[..., AbstractContextManager[object]]) -> Generator[None, None, None]:
    """Point the EP client at the respx test base URL and supply a dummy JWT."""
    with (
        override_settings(ep_api_url=_EP_BASE),
        patch.object(ep_client_module, "create_ep_service_token", return_value="test-token"),
    ):
        yield


class TestExecutionTargetsPagination:
    """Execution-target list endpoint uses BaseListParams and forwards limit to EP."""

    @pytest.mark.asyncio
    async def test_first_page_returns_resources(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            ep.get("/v1/execution-targets").mock(return_value=Response(200, json=[_TARGET_1, _TARGET_2]))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"limit": 2},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["resources"]) == 2
        assert body["resources"][0]["name"] == "workers-1"
        assert body["resources"][1]["name"] == "workers-2"
        assert "next" in body
        assert "prev" in body
        assert "total" in body

    @pytest.mark.asyncio
    async def test_limit_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            route = ep.get("/v1/execution-targets").mock(return_value=Response(200, json=[_TARGET_1]))
            await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"limit": 7},
            )

        assert "limit=7" in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    async def test_cursor_accepted_but_not_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Cursor is a valid query param (BaseListParams) but EP does not support it."""
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            route = ep.get("/v1/execution-targets").mock(return_value=Response(200, json=[_TARGET_2]))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"limit": 1, "cursor": "some_opaque_cursor"},
            )

        assert resp.status_code == 200
        assert "cursor" not in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    async def test_sort_accepted(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE) as ep:
            ep.get("/v1/execution-targets").mock(return_value=Response(200, json=[]))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"sort": "-created_at"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_include_total_accepted(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE) as ep:
            ep.get("/v1/execution-targets").mock(return_value=Response(200, json=[]))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"include_total": "true"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_limit_too_low_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        resp = await auth_client.get(
            "/api/execution_plane/v1/execution_targets",
            params={"limit": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_limit_too_high_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        resp = await auth_client.get(
            "/api/execution_plane/v1/execution_targets",
            params={"limit": 101},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_sort_pattern_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        resp = await auth_client.get(
            "/api/execution_plane/v1/execution_targets",
            params={"sort": "INVALID SORT"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ep_unavailable_returns_503(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE) as ep:
            ep.get("/v1/execution-targets").mock(return_value=Response(503))
            resp = await auth_client.get("/api/execution_plane/v1/execution_targets")

        assert resp.status_code == 503


class TestWorkItemsPagination:
    """Work-item list endpoint uses BaseListParams and forwards limit to EP."""

    @pytest.mark.asyncio
    async def test_returns_resources(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            ep.get("/v1/work-items").mock(return_value=Response(200, json=[_WORK_ITEM_1]))
            resp = await auth_client.get(
                "/api/execution_plane/v1/work_items",
                params={"limit": 1},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["resources"]) == 1
        assert body["resources"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_limit_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            route = ep.get("/v1/work-items").mock(return_value=Response(200, json=[]))
            await auth_client.get(
                "/api/execution_plane/v1/work_items",
                params={"limit": 5},
            )

        assert "limit=5" in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    async def test_invalid_limit_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        resp = await auth_client.get(
            "/api/execution_plane/v1/work_items",
            params={"limit": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ep_unavailable_returns_503(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with respx.mock(base_url=_EP_BASE) as ep:
            ep.get("/v1/work-items").mock(return_value=Response(503))
            resp = await auth_client.get("/api/execution_plane/v1/work_items")

        assert resp.status_code == 503
