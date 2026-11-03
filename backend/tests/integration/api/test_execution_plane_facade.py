"""Integration tests for the AO Execution Plane facade pagination contract.

Query controls, dynamic bracket filters, and opaque cursors are forwarded to EP.
EP's response envelope and validation errors retain their public semantics.

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
    """Execution-target list endpoint forwards query controls and the EP page envelope."""

    @pytest.mark.asyncio
    async def test_first_page_returns_resources(
        self,
        auth_client: AsyncClient,
    ) -> None:
        ep_page: dict[str, Any] = {
            "resources": [_TARGET_1, _TARGET_2],
            "next": "eyJpZCI6Im5leHQifQ",
            "prev": None,
            "total": None,
        }
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            ep.get("/v1/execution-targets").mock(return_value=Response(200, json=ep_page))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"limit": 2},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["resources"]) == 2
        assert body["resources"][0]["name"] == "workers-1"
        assert body["resources"][1]["name"] == "workers-2"
        assert body["next"] == "eyJpZCI6Im5leHQifQ"
        assert body["prev"] is None
        assert body["total"] is None

    @pytest.mark.asyncio
    async def test_limit_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        ep_page: dict[str, Any] = {"resources": [_TARGET_1], "next": None, "prev": None, "total": None}
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            route = ep.get("/v1/execution-targets").mock(return_value=Response(200, json=ep_page))
            await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"limit": 7},
            )

        assert "limit=7" in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    async def test_cursor_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Cursor is forwarded to EP and EP's next/prev cursors are passed through."""
        ep_page: dict[str, Any] = {"resources": [_TARGET_2], "next": None, "prev": "eyJpZCI6InByZXYifQ", "total": None}
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            route = ep.get("/v1/execution-targets").mock(return_value=Response(200, json=ep_page))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"limit": 1, "cursor": "some_opaque_cursor"},
            )

        assert resp.status_code == 200
        assert "cursor=some_opaque_cursor" in str(route.calls.last.request.url)
        assert resp.json()["prev"] == "eyJpZCI6InByZXYifQ"

    @pytest.mark.asyncio
    async def test_sort_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        ep_page: dict[str, Any] = {"resources": [], "next": None, "prev": None, "total": None}
        with respx.mock(base_url=_EP_BASE) as ep:
            route = ep.get("/v1/execution-targets").mock(return_value=Response(200, json=ep_page))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"sort": "-created_at"},
            )

        assert resp.status_code == 200
        assert "sort=-created_at" in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    async def test_include_total_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        ep_page: dict[str, Any] = {"resources": [], "next": None, "prev": None, "total": 42}
        with respx.mock(base_url=_EP_BASE) as ep:
            route = ep.get("/v1/execution-targets").mock(return_value=Response(200, json=ep_page))
            resp = await auth_client.get(
                "/api/execution_plane/v1/execution_targets",
                params={"include_total": "true"},
            )

        assert resp.status_code == 200
        assert "include_total=true" in str(route.calls.last.request.url)
        assert resp.json()["total"] == 42

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
    """Work-item list endpoint forwards query controls and the EP page envelope."""

    @pytest.mark.asyncio
    async def test_returns_resources(
        self,
        auth_client: AsyncClient,
    ) -> None:
        ep_page: dict[str, Any] = {"resources": [_WORK_ITEM_1], "next": None, "prev": None, "total": None}
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            ep.get("/v1/work-items").mock(return_value=Response(200, json=ep_page))
            resp = await auth_client.get(
                "/api/execution_plane/v1/work_items",
                params={"limit": 1},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["resources"]) == 1
        assert body["resources"][0]["status"] == "completed"
        assert body["next"] is None

    @pytest.mark.asyncio
    async def test_limit_forwarded_to_ep(
        self,
        auth_client: AsyncClient,
    ) -> None:
        ep_page: dict[str, Any] = {"resources": [], "next": None, "prev": None, "total": None}
        with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
            route = ep.get("/v1/work-items").mock(return_value=Response(200, json=ep_page))
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


LIST_ENDPOINTS = [
    ("/api/execution_plane/v1/work_items", "/v1/work-items"),
    ("/api/execution_plane/v1/execution_targets", "/v1/execution-targets"),
]


@pytest.mark.parametrize(
    ("resource_id", "ep_status", "ep_body", "expected_ids"),
    [
        pytest.param(
            "7beaf7e4-0000-4000-8000-000000000099",
            200,
            {"resources": [], "next": None, "prev": None, "total": None},
            [],
            id="GET /execution_targets?id=missing-uuid&limit=1 -> 200 empty",
        ),
        pytest.param(
            "abc123",
            422,
            {"detail": "badly formed hexadecimal UUID string"},
            [],
            id="GET /execution_targets?id=abc123&limit=1 -> 422",
        ),
        pytest.param(
            _TARGET_2["id"],
            200,
            {"resources": [_TARGET_2], "next": None, "prev": None, "total": None},
            [_TARGET_2["id"]],
            id="GET /execution_targets?id=second-target-uuid&limit=1 -> matching target",
        ),
    ],
)
async def test_get_execution_targets_by_plain_id_with_limit_one(
    auth_client: AsyncClient,
    resource_id: str,
    ep_status: int,
    ep_body: dict[str, Any],
    expected_ids: list[str],
) -> None:
    """Forward plain id with limit=1; preserve empty results, UUID errors, and matches.

    PostgreSQL backs AO authentication. EP HTTP is mocked: this tests the facade
    boundary, while EP's PostgreSQL tests cover actual database filtering.
    """
    query = {"id": resource_id, "limit": "1"}
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        route = ep.get("/v1/execution-targets", params=query).mock(return_value=Response(ep_status, json=ep_body))
        response = await auth_client.get("/api/execution_plane/v1/execution_targets", params=query)

    assert route.call_count == 1
    assert dict(route.calls.last.request.url.params) == query
    assert response.status_code == ep_status, response.text
    if ep_status == 422:
        assert response.json()["detail"] == ep_body["detail"]
    else:
        body = response.json()
        assert [target["id"] for target in body["resources"]] == expected_ids
        assert body["next"] is None
        assert body["prev"] is None
        assert body["total"] is None


FORWARDED_QUERIES = [
    {"id[in]": "aaaaaaaa-0000-4000-8000-000000000001,aaaaaaaa-0000-4000-8000-000000000002"},
    {"status[in]": "pending,failed", "created_at[gte]": "2025-06-01T12:00:00+00:00"},
    {"id[in]": ""},
    {"sort": "-status", "limit": "2", "include_total": "true", "cursor": "opaque+/=cursor"},
    {"unknown[operator]": "preserve-for-ep-validation"},
]


@pytest.mark.parametrize(("path", "ep_path"), LIST_ENDPOINTS, ids=[p for p, _ in LIST_ENDPOINTS])
@pytest.mark.parametrize("query", FORWARDED_QUERIES, ids=[f"GET {q}" for q in FORWARDED_QUERIES])
async def test_get_list_forwards_query_values_unchanged(
    auth_client: AsyncClient,
    path: str,
    ep_path: str,
    query: dict[str, str],
) -> None:
    ep_page: dict[str, Any] = {"resources": [], "next": "next+/=", "prev": "prev+/=", "total": 7}
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        route = ep.get(ep_path).mock(return_value=Response(200, json=ep_page))
        response = await auth_client.get(path, params=query)
    assert response.status_code == 200, response.text
    forwarded = dict(route.calls.last.request.url.params)
    assert forwarded == {"limit": "20", **query}
    assert response.json() == ep_page


@pytest.mark.parametrize(
    "query",
    [
        {"labels[env]": "", "labels[region]": "west"},
        {"name[contains]": "worker", "enabled": "false", "is_default": "true"},
        {"sort": "name", "cluster_id": "aaaaaaaa-0000-4000-8000-000000000001", "backend_type": "vanilla_k8s"},
    ],
    ids=lambda query: f"GET /execution_targets {query}",
)
async def test_get_targets_forwards_named_boolean_and_label_filters(
    auth_client: AsyncClient,
    query: dict[str, str],
) -> None:
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        route = ep.get("/v1/execution-targets").mock(return_value=Response(200, json={"resources": []}))
        response = await auth_client.get("/api/execution_plane/v1/execution_targets", params=query)
    assert response.status_code == 200, response.text
    assert dict(route.calls.last.request.url.params) == {"limit": "20", **query}


@pytest.mark.parametrize(("path", "ep_path"), LIST_ENDPOINTS, ids=[p for p, _ in LIST_ENDPOINTS])
async def test_get_list_omits_unspecified_sort_to_preserve_ep_default(
    auth_client: AsyncClient, path: str, ep_path: str
) -> None:
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        route = ep.get(ep_path).mock(return_value=Response(200, json={"resources": []}))
        response = await auth_client.get(path)
    assert response.status_code == 200, response.text
    assert dict(route.calls.last.request.url.params) == {"limit": "20"}


@pytest.mark.parametrize(("path", "ep_path"), LIST_ENDPOINTS, ids=[p for p, _ in LIST_ENDPOINTS])
async def test_get_list_preserves_ep_422_validation_error(auth_client: AsyncClient, path: str, ep_path: str) -> None:
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        route = ep.get(ep_path).mock(return_value=Response(422, json={"detail": "Invalid field: id__in"}))
        response = await auth_client.get(path, params={"id__in": "bad-id"})
    assert response.status_code == 422, response.text
    assert route.calls.last.request.url.params["id__in"] == "bad-id"
    assert response.json()["detail"] == "Invalid field: id__in"


@pytest.mark.parametrize(("path", "ep_path"), LIST_ENDPOINTS, ids=[p for p, _ in LIST_ENDPOINTS])
@pytest.mark.parametrize("ep_status", [401, 403, 404], ids=lambda code: f"EP {code} -> AO 502")
async def test_get_list_maps_service_rejection_to_bad_gateway(
    auth_client: AsyncClient,
    path: str,
    ep_path: str,
    ep_status: int,
) -> None:
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        ep.get(ep_path).mock(return_value=Response(ep_status, json={"detail": "internal service error"}))
        response = await auth_client.get(path)
    assert response.status_code == 502, response.text
    assert "internal service error" not in response.text


INVALID_PAGES = [
    [],
    {},
    {"resources": None},
    {"resources": {}},
    {"resources": [1]},
    {"resources": [], "next": 1},
    {"resources": [], "prev": []},
    {"resources": [], "total": -1},
    {"resources": [], "total": True},
    {"resources": [{"id": "invalid-resource"}]},
]


@pytest.mark.parametrize(("path", "ep_path"), LIST_ENDPOINTS, ids=[p for p, _ in LIST_ENDPOINTS])
@pytest.mark.parametrize("page", INVALID_PAGES, ids=lambda page: f"EP page={page!r} -> AO 502")
async def test_get_list_rejects_malformed_upstream_page(
    auth_client: AsyncClient,
    path: str,
    ep_path: str,
    page: Any,  # noqa: ANN401 - deliberately malformed JSON values
) -> None:
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        ep.get(ep_path).mock(return_value=Response(200, json=page))
        response = await auth_client.get(path)
    assert response.status_code == 502, response.text


@pytest.mark.parametrize(("path", "ep_path"), LIST_ENDPOINTS, ids=[p for p, _ in LIST_ENDPOINTS])
async def test_get_list_rejects_invalid_upstream_json(auth_client: AsyncClient, path: str, ep_path: str) -> None:
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        ep.get(ep_path).mock(return_value=Response(200, text="not-json"))
        response = await auth_client.get(path)
    assert response.status_code == 502, response.text
