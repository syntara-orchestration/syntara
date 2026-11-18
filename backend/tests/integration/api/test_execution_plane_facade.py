"""Integration tests for the AO Execution Plane facade authorization and proxy contracts.

Query controls, dynamic bracket filters, and opaque cursors are forwarded to EP.
EP's response envelope and validation errors retain their public semantics.

EP HTTP calls are intercepted by respx; the AO database and Rego evaluation are real.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch
from uuid import uuid4

import pytest
import respx
from execution_plane_client.catalog import CommandCatalog
from execution_plane_client.protocol import MessageEnvelope
from httpx import AsyncClient, Request, Response
from sqlalchemy import insert

from syntara.authz.models import Policy, Project, Role, RoleAssignment
from syntara.core.models.group import Group, user_groups
from syntara.execution_plane import client as ep_client_module

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator
    from contextlib import AbstractContextManager

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_EP_BASE = "https://ep.test"

_TARGET_1: dict[str, Any] = {
    "id": "7beaf7e4-0000-4000-8000-000000000001",
    "cluster_id": "7beaf7e4-0000-4000-8000-000000000002",
    "name": "workers-1",
    "backend_type": "kubernetes",
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
    "status_message": None,
    "labels": {},
    "created_at": "2026-10-01T00:00:00Z",
    "last_ran_at": None,
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
    "resource_cleanup_status": "completed",
    "resource_cleanup_error": None,
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

    @pytest.mark.asyncio
    async def test_invalid_sort_field_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Validate sort field against EP sortable fields metadata."""
        # last_ran_at is filterable but NOT sortable
        resp = await auth_client.get(
            "/api/execution_plane/v1/execution_targets",
            params={"sort": "last_ran_at"},
        )
        assert resp.status_code == 422
        assert "Invalid sort field: last_ran_at" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_filter_field_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Validate filter fields against EP metadata before forwarding."""
        resp = await auth_client.get(
            "/api/execution_plane/v1/execution_targets",
            params={"invalid_field": "value"},
        )
        assert resp.status_code == 422
        assert "Invalid filter field: invalid_field" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_bracket_operator_validated(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Bracket operators like id[in] are validated against base field."""
        resp = await auth_client.get(
            "/api/execution_plane/v1/execution_targets",
            params={"invalid_field[in]": "value"},
        )
        assert resp.status_code == 422
        assert "Invalid filter field: invalid_field" in resp.json()["detail"]


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

    @pytest.mark.asyncio
    async def test_invalid_sort_field_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Validate sort field against work item sortable fields."""
        # claimed_at is filterable but NOT sortable
        resp = await auth_client.get(
            "/api/execution_plane/v1/work_items",
            params={"sort": "claimed_at"},
        )
        assert resp.status_code == 422
        assert "Invalid sort field: claimed_at" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_labels_not_supported_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Work items don't support label filtering."""
        resp = await auth_client.get(
            "/api/execution_plane/v1/work_items",
            params={"labels[env]": "prod"},
        )
        assert resp.status_code == 422
        assert "Label filtering not supported" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_filter_field_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Validate filter fields against EP metadata before forwarding."""
        resp = await auth_client.get(
            "/api/execution_plane/v1/work_items",
            params={"invalid_field": "value"},
        )
        assert resp.status_code == 422
        assert "Invalid filter field: invalid_field" in resp.json()["detail"]


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
        {"sort": "name", "cluster_id": "aaaaaaaa-0000-4000-8000-000000000001", "backend_type": "kubernetes"},
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
    """EP still validates cursor format and other non-field errors."""
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        route = ep.get(ep_path).mock(return_value=Response(422, json={"detail": "Invalid cursor format"}))
        response = await auth_client.get(path, params={"cursor": "invalid-base64"})
    assert response.status_code == 422, response.text
    assert route.calls.last.request.url.params["cursor"] == "invalid-base64"
    assert response.json()["detail"] == "Invalid cursor format"


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


@pytest.mark.parametrize(
    "query",
    [
        {"runtime_context[project_id]": "project", "runtime_context[execution_id]": ""},
        {"runtime_context[nested.key]": "a,b", "include_total": "true", "limit": "1"},
    ],
)
async def test_work_runtime_context_filters_are_forwarded_unchanged(
    auth_client: AsyncClient, query: dict[str, str]
) -> None:
    page: dict[str, Any] = {"resources": [], "next": None, "prev": None, "total": 0}
    with respx.mock(base_url=_EP_BASE, assert_all_called=True) as ep:
        route = ep.get("/v1/work-items").mock(return_value=Response(200, json=page))
        response = await auth_client.get("/api/execution_plane/v1/work_items", params=query)
    assert response.status_code == 200, response.text
    assert dict(route.calls.last.request.url.params) == {"limit": "20", **query}
    assert response.json() == page


@pytest.mark.parametrize("key", ["runtime_context", "runtime_context[]", "runtime_context[x][eq]"])
async def test_malformed_context_filters_are_rejected_before_ep(auth_client: AsyncClient, key: str) -> None:
    with respx.mock(assert_all_called=False) as ep:
        response = await auth_client.get("/api/execution_plane/v1/work_items", params={key: "value"})
    assert response.status_code == 422
    assert not ep.calls


# Each operation is exercised through real policy resolution and Rego. Only the
# outbound EP HTTP boundary is mocked, using the shared command/receipt contract.
_PREFIX = "/api/execution_plane/v1"
_TARGET_PATH = f"{_PREFIX}/execution_targets/{_TARGET_1['id']}"
_CREATE_BODY = {"name": "workers", "placement": {"type": "kubernetes", "namespace": "workers"}}
_OPERATIONS = [
    ("GET", f"{_PREFIX}/execution_targets", None, "execution_target:read", 200),
    ("GET", _TARGET_PATH, None, "execution_target:read", 200),
    ("GET", f"{_TARGET_PATH}/health", None, "execution_target:read", 200),
    ("GET", f"{_TARGET_PATH}/usage", None, "execution_target:read", 200),
    ("POST", f"{_PREFIX}/execution_targets", _CREATE_BODY, "execution_target:create", 201),
    ("PATCH", _TARGET_PATH, {"enabled": False}, "execution_target:update", 200),
    ("DELETE", _TARGET_PATH, None, "execution_target:delete", 202),
    ("GET", f"{_PREFIX}/work_items", None, "work_item:read", 200),
]
_PERMISSIONS = sorted({operation[3] for operation in _OPERATIONS})


@pytest.fixture
def ep_inventory() -> Generator[respx.MockRouter, None, None]:
    """Serve inventory and valid target command receipts through real HTTP transport."""
    target = dict(_TARGET_1)

    def command_response(request: Request) -> Response:
        message = MessageEnvelope.model_validate_json(request.content)
        CommandCatalog().validate(message)
        target["id"] = message.command.payload["resource_id"]
        result = None
        if message.command.command_type == "execution_target.health":
            result = {
                "command_type": "execution_target.health",
                "command_revision": 1,
                "healthy": True,
                "message": "probe succeeded",
                "skipped": False,
            }
        return Response(
            200,
            json={
                "received": True,
                "message_id": str(message.message_id),
                "resource": {"kind": "execution_target", "resource_id": target["id"]},
                "result": result,
            },
        )

    with respx.mock(base_url=_EP_BASE, assert_all_called=False) as ep:
        ep.get("/v1/execution-targets").respond(200, json={"resources": [target], "total": 1})
        ep.get(url__regex=r"/v1/execution-targets/[^/]+$").mock(side_effect=lambda _request: Response(200, json=target))
        ep.get("/v1/work-items").respond(200, json={"resources": [_WORK_ITEM_1], "total": 1})
        ep.get("/v1/clusters").respond(
            200,
            json={
                "resources": [
                    {
                        "id": _TARGET_1["cluster_id"],
                        "endpoint": _TARGET_1["endpoint"],
                    }
                ]
            },
        )
        ep.post("/v1/commands").mock(side_effect=command_response)
        yield ep


@pytest.mark.parametrize(("method", "path", "body", "permission", "success"), _OPERATIONS)
@pytest.mark.parametrize("grant", ["none", "user", "project-admin", "auditor", "admin", *_PERMISSIONS])
async def test_facade_permission_matrix(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
    ep_inventory: respx.MockRouter,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    permission: str,
    success: int,
    grant: str,
) -> None:
    """Named roles and single-permission custom roles enforce every facade operation."""
    user = await user_factory(group_names=[])
    if grant in _PERMISSIONS:
        role = Role(name=f"ep-role-{uuid4()}", policy_names=[f"{grant}:any"])
        test_db_session.add(role)
        await test_db_session.flush()
        test_db_session.add(RoleAssignment(principal_id=user.id, role_name=role.name))
    elif grant == "project-admin":
        project = Project(name=f"ep-project-{uuid4()}")
        test_db_session.add(project)
        await test_db_session.flush()
        test_db_session.add(RoleAssignment(principal_id=user.id, role_name=grant, project_id=project.id))
    elif grant != "none":
        test_db_session.add(RoleAssignment(principal_id=user.id, role_name=grant))
    await test_db_session.commit()
    auth_as(user)

    resource_type, action = permission.split(":")
    expected = grant in ("admin", permission) or (grant == "auditor" and action == "read")
    can_i = await auth_client.post("/api/v1/authz/can_i", json={"resource_type": resource_type, "action": action})
    assert can_i.status_code == 200, can_i.text
    assert can_i.json()["allowed"] is expected

    response = await auth_client.request(method, path, json=body)
    assert response.status_code == (success if expected else 403), response.text
    if expected:
        assert ep_inventory.calls
        if method == "GET" and path in (f"{_PREFIX}/execution_targets", f"{_PREFIX}/work_items"):
            assert len(response.json()["resources"]) == 1
            assert response.json()["total"] == 1
    else:
        assert not ep_inventory.calls
        assert "resources" not in response.json()
        assert "total" not in response.json()
        assert "next" not in response.json()


@pytest.mark.parametrize(
    ("path", "resource_type"),
    [
        (f"{_PREFIX}/execution_targets", "execution_target"),
        (f"{_PREFIX}/work_items", "work_item"),
    ],
)
async def test_project_grant_cannot_unlock_global_ep_inventory(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
    ep_inventory: respx.MockRouter,
    path: str,
    resource_type: str,
) -> None:
    """Even a persisted project EP grant must not authorize the unfiltered list.

    The policy API rejects these grants today; seed one directly to reproduce
    the old ProjectScopeFilter loophole and protect against legacy policy data.
    """
    user = await user_factory(group_names=[])
    project = Project(name=f"ep-project-{uuid4()}")
    test_db_session.add(project)
    await test_db_session.flush()
    policy = Policy(
        name=f"ep-policy-{uuid4()}",
        project_id=project.id,
        scope="project",
        statements=[
            {
                "effect": "allow",
                "actions": [f"{resource_type}:read"],
                "scope": "project",
            }
        ],
    )
    role = Role(name=f"ep-role-{uuid4()}", project_id=project.id, scope="project", policy_names=[policy.name])
    test_db_session.add_all([policy, role])
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(principal_id=user.id, role_name=role.name, project_id=project.id))
    await test_db_session.commit()
    auth_as(user)

    query = {"include_total": "true", "cursor": "opaque-cursor"}
    if resource_type == "work_item":
        query["runtime_context[project_id]"] = str(project.id)
    response = await auth_client.get(path, params=query)
    assert response.status_code == 403, response.text
    assert not ep_inventory.calls


async def test_group_role_grant_and_revocation(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
    ep_inventory: respx.MockRouter,
) -> None:
    """Group membership grants target reads, and revoking the role removes them."""
    user = await user_factory(group_names=[])
    auth_as(user)
    path = f"{_PREFIX}/execution_targets"
    assert (await auth_client.get(path)).status_code == 403
    assert not ep_inventory.calls

    role = Role(name=f"ep-role-{uuid4()}", policy_names=["execution_target:read:any"])
    group = Group(name=f"ep-group-{uuid4()}")
    test_db_session.add_all([role, group])
    await test_db_session.flush()
    assignment = RoleAssignment(group_id=group.id, role_name=role.name)
    test_db_session.add(assignment)
    await test_db_session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await test_db_session.commit()
    response = await auth_client.get(path)
    assert response.status_code == 200, response.text
    assert response.json()["resources"][0]["id"] == _TARGET_1["id"]

    await test_db_session.delete(assignment)
    await test_db_session.commit()
    call_count = len(ep_inventory.calls)
    assert (await auth_client.get(path)).status_code == 403
    assert len(ep_inventory.calls) == call_count


@pytest.mark.parametrize("effect", ["allow", "deny"])
@pytest.mark.parametrize("matches", [False, True])
async def test_facade_evaluates_policy_conditions_and_denies(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
    ep_inventory: respx.MockRouter,
    effect: str,
    *,
    matches: bool,
) -> None:
    """Evaluate user-label conditions and deny precedence without mocking Rego."""
    user = await user_factory(group_names=[], labels={"team": "operations" if matches else "other"})
    policy = Policy(
        name=f"ep-policy-{uuid4()}",
        statements=[
            {
                "effect": effect,
                "actions": ["execution_target:read"],
                "scope": "any",
                "conditions": {"user_labels": {"team": "operations"}},
            }
        ],
    )
    # Deny creation is intentionally disabled in the policy API. Persist the
    # fixture directly to exercise the evaluator's existing deny precedence.
    policies = [policy.name]
    if effect == "deny":
        policies.append("execution_target:read:any")
    role = Role(name=f"ep-role-{uuid4()}", policy_names=policies)
    test_db_session.add_all([policy, role])
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(principal_id=user.id, role_name=role.name))
    await test_db_session.commit()
    auth_as(user)

    expected = matches if effect == "allow" else not matches
    response = await auth_client.get(f"{_PREFIX}/execution_targets")
    assert response.status_code == (200 if expected else 403), response.text
    assert bool(ep_inventory.calls) is expected


async def test_ep_permission_catalog_and_project_policy_validation(auth_client: AsyncClient) -> None:
    """EP permissions are discoverable and cannot be added to project policies."""
    catalog = await auth_client.get("/api/v1/authz/resource_actions")
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["resource_actions"]["execution_target"] == ["create", "delete", "read", "update"]
    assert catalog.json()["resource_actions"]["work_item"] == ["read"]

    project = await auth_client.post("/api/v1/projects", json={"name": f"ep-project-{uuid4()}"})
    assert project.status_code == 201, project.text
    for permission in _PERMISSIONS:
        response = await auth_client.post(
            f"/api/v1/projects/{project.json()['id']}/policies",
            json={
                "name": f"ep-policy-{uuid4()}",
                "statements": [{"effect": "allow", "actions": [permission], "scope": "project"}],
            },
        )
        assert response.status_code == 422, response.text
