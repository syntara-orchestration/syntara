"""Terraform HTTP request contracts, including safe deletion defaults."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from syntara.terraform.client import (
    DEFAULT_TFE_HTTP_TIMEOUT_SECONDS,
    TFEClient,
    _extract_error_detail,
    _terminal_transport_error,
    resolve_http_timeout_from_engine,
)
from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.presets import workspace_preset_parts

BASE_URL = "https://terraform.example.com/api/v2"


@pytest.fixture
def client() -> TFEClient:
    return TFEClient(base_url="https://terraform.example.com", token="test", organization="acme")  # noqa: S106


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real sleep during retry backoff in unit tests."""
    monkeypatch.setattr("syntara.terraform.client.asyncio.sleep", AsyncMock())


def test_resolve_http_timeout_from_engine_leaves_margin() -> None:
    """Client HTTP budget must stay under the activity timeout."""
    assert resolve_http_timeout_from_engine(180) == 170.0
    assert resolve_http_timeout_from_engine(900) == 890.0
    assert resolve_http_timeout_from_engine(5) == 1.0
    assert resolve_http_timeout_from_engine(None) == DEFAULT_TFE_HTTP_TIMEOUT_SECONDS


def test_request_timeout_divides_budget_for_reads() -> None:
    """Read retries share the activity HTTP budget; mutating calls use the full budget."""
    client = TFEClient(
        base_url="https://terraform.example.com",
        token="test",  # noqa: S106
        organization="acme",
        timeout_seconds=170.0,
    )
    assert client._request_timeout(mutating=True) == 170.0
    assert client._request_timeout(mutating=False) == pytest.approx(170.0 / 3)


def test_url_passthrough_for_absolute_paths(client: TFEClient) -> None:
    absolute = "https://uploads.example.com/artifact"
    assert client._url(absolute) == absolute
    assert client._url("/workspaces/ws-1") == f"{BASE_URL}/workspaces/ws-1"


def test_next_page_from_pagination_metadata(client: TFEClient) -> None:
    assert client._next_page({"meta": {"pagination": {"next-page": 2}}}, 1) == 2
    assert client._next_page({"meta": {"pagination": {"next-page": 0}}}, 1) is None
    assert client._next_page({"meta": {"pagination": {"total-pages": 3}}}, 2) == 3
    assert client._next_page({"meta": {"pagination": {"total-pages": 2}}}, 2) is None
    assert client._next_page({"links": {"next": "https://example.com?page=2"}}, 1) == 2
    assert client._next_page({"data": []}, 1) is None


def test_merge_pages_strips_stale_pagination(client: TFEClient) -> None:
    merged = client._merge_pages(
        {"data": [{"id": "1"}], "links": {"next": "x"}, "meta": {"pagination": {"next-page": 2}, "status-counts": {}}},
        [{"id": "1"}, {"id": "2"}],
    )
    assert merged["data"] == [{"id": "1"}, {"id": "2"}]
    assert "links" not in merged
    assert "pagination" not in merged["meta"]
    assert merged["meta"]["status-counts"] == {}

    empty_meta = client._merge_pages({"data": [], "meta": {"pagination": {"next-page": 2}}}, [{"id": "a"}])
    assert "meta" not in empty_meta


def test_terminal_transport_error_mutating_is_outcome_unknown() -> None:
    err = _terminal_transport_error(httpx.ConnectError("x"), mutating=True, attempt=1, attempts=3)
    assert err is not None
    assert err.error_code == TFEErrorCode.OUTCOME_UNKNOWN


def test_terminal_transport_error_read_retries_then_unreachable() -> None:
    assert _terminal_transport_error(httpx.ConnectError("x"), mutating=False, attempt=1, attempts=3) is None
    timeout = _terminal_transport_error(httpx.ReadTimeout("t"), mutating=False, attempt=3, attempts=3)
    assert timeout is not None
    assert timeout.error_code == TFEErrorCode.UNREACHABLE
    assert "timed out" in timeout.message
    network = _terminal_transport_error(httpx.ConnectError("c"), mutating=False, attempt=3, attempts=3)
    assert network is not None
    assert network.error_code == TFEErrorCode.UNREACHABLE
    assert "unreachable" in network.message


def test_extract_error_detail_from_json_api() -> None:
    response = httpx.Response(
        422,
        json={"errors": [{"title": "Invalid", "detail": "name is required"}, {"title": "Conflict"}]},
    )
    assert _extract_error_detail(response) == "Invalid: name is required; Conflict"


def test_extract_error_detail_fallback_for_non_json() -> None:
    response = httpx.Response(500, text="not-json")
    assert _extract_error_detail(response) == "TFE API returned HTTP 500"


@pytest.mark.asyncio
@respx.mock
async def test_default_delete_uses_safe_delete(client: TFEClient) -> None:
    route = respx.post(f"{BASE_URL}/workspaces/ws-1/actions/safe-delete").mock(return_value=httpx.Response(204))
    await client.delete_workspace("ws-1")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_force_delete_requires_explicit_opt_in(client: TFEClient) -> None:
    route = respx.delete(f"{BASE_URL}/workspaces/ws-1").mock(return_value=httpx.Response(204))
    await client.delete_workspace("ws-1", force=True)
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_variable_mutations_are_workspace_scoped(client: TFEClient) -> None:
    update = respx.patch(f"{BASE_URL}/workspaces/ws-1/vars/var-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "var-1"}})
    )
    delete = respx.delete(f"{BASE_URL}/workspaces/ws-1/vars/var-1").mock(return_value=httpx.Response(204))
    await client.update_variable("ws-1", "var-1", {"value": "updated"})
    await client.delete_variable("ws-1", "var-1")
    assert json.loads(update.calls[0].request.content)["data"]["attributes"] == {"value": "updated"}
    assert delete.called


@pytest.mark.asyncio
@respx.mock
async def test_github_installation_endpoints(client: TFEClient) -> None:
    listing = respx.get(f"{BASE_URL}/github-app/installations").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    detail = respx.get(f"{BASE_URL}/github-app/installation/ghain-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "ghain-1"}})
    )
    await client.list_github_app_installations()
    await client.get_github_app_installation("ghain-1")
    assert listing.called
    assert detail.called


@pytest.mark.asyncio
@respx.mock
async def test_agent_pool_is_sent_as_workspace_attribute(client: TFEClient) -> None:
    route = respx.post(f"{BASE_URL}/organizations/acme/workspaces").mock(
        return_value=httpx.Response(201, json={"data": {"id": "ws-1"}})
    )
    attributes, relationships = workspace_preset_parts("agent", agent_pool_id="apool-1")
    await client.create_workspace("demo", attributes=attributes, relationships=relationships)
    data = json.loads(route.calls[0].request.content)["data"]
    assert data["attributes"]["agent-pool-id"] == "apool-1"
    assert "relationships" not in data


@pytest.mark.asyncio
@respx.mock
async def test_create_workspace_with_project_relationship(client: TFEClient) -> None:
    route = respx.post(f"{BASE_URL}/organizations/acme/workspaces").mock(
        return_value=httpx.Response(201, json={"data": {"id": "ws-1"}})
    )
    await client.create_workspace("demo", project_id="prj-1")
    body = json.loads(route.calls[0].request.content)["data"]
    assert body["relationships"]["project"]["data"]["id"] == "prj-1"


@pytest.mark.asyncio
@respx.mock
async def test_list_workspaces_paginates_and_filters(client: TFEClient) -> None:
    page1 = respx.get(f"{BASE_URL}/organizations/acme/workspaces").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "data": [{"id": "ws-1"}],
                    "meta": {"pagination": {"next-page": 2, "total-pages": 2}},
                    "links": {"next": "n"},
                },
            ),
            httpx.Response(
                200,
                json={"data": [{"id": "ws-2"}], "meta": {"pagination": {"next-page": None, "total-pages": 2}}},
            ),
        ]
    )
    result = await client.list_workspaces(search="demo", project_id="prj-1")
    assert [item["id"] for item in result["data"]] == ["ws-1", "ws-2"]
    assert "links" not in result
    assert page1.call_count == 2
    assert page1.calls[0].request.url.params["search[name]"] == "demo"
    assert page1.calls[0].request.url.params["filter[project][id]"] == "prj-1"


@pytest.mark.asyncio
@respx.mock
async def test_update_workspace_with_relationships(client: TFEClient) -> None:
    route = respx.patch(f"{BASE_URL}/workspaces/ws-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "ws-1"}})
    )
    await client.update_workspace("ws-1", {"name": "n"}, relationships={"project": {"data": None}})
    body = json.loads(route.calls[0].request.content)["data"]
    assert body["attributes"] == {"name": "n"}
    assert body["relationships"] == {"project": {"data": None}}


@pytest.mark.asyncio
@respx.mock
async def test_get_current_state_version_returns_none_on_404(client: TFEClient) -> None:
    respx.get(f"{BASE_URL}/workspaces/ws-1/current-state-version").mock(return_value=httpx.Response(404, json={}))
    assert await client.get_current_state_version("ws-1") is None


@pytest.mark.asyncio
@respx.mock
async def test_get_current_state_version_reraises_non_404(client: TFEClient) -> None:
    respx.get(f"{BASE_URL}/workspaces/ws-1/current-state-version").mock(return_value=httpx.Response(403, json={}))
    with pytest.raises(TFEError) as exc_info:
        await client.get_current_state_version("ws-1")
    assert exc_info.value.error_code == TFEErrorCode.AUTHZ_FAILED


@pytest.mark.asyncio
@respx.mock
async def test_get_state_version_outputs_and_list_variables(client: TFEClient) -> None:
    outputs = respx.get(f"{BASE_URL}/state-versions/sv-1/outputs").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "out-1"}]})
    )
    vars_route = respx.get(f"{BASE_URL}/workspaces/ws-1/vars").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "var-1"}]})
    )
    assert (await client.get_state_version_outputs("sv-1"))["data"][0]["id"] == "out-1"
    assert (await client.list_variables("ws-1"))["data"][0]["id"] == "var-1"
    assert outputs.called
    assert vars_route.called


@pytest.mark.asyncio
@respx.mock
async def test_create_variable_and_configuration_version(client: TFEClient) -> None:
    var_route = respx.post(f"{BASE_URL}/workspaces/ws-1/vars").mock(
        return_value=httpx.Response(201, json={"data": {"id": "var-1"}})
    )
    cv_route = respx.post(f"{BASE_URL}/workspaces/ws-1/configuration-versions").mock(
        return_value=httpx.Response(201, json={"data": {"id": "cv-1"}})
    )
    await client.create_variable("ws-1", {"key": "K", "value": "V"})
    await client.create_configuration_version("ws-1", auto_queue_runs=True, speculative=True)
    assert json.loads(var_route.calls[0].request.content)["data"]["attributes"]["key"] == "K"
    attrs = json.loads(cv_route.calls[0].request.content)["data"]["attributes"]
    assert attrs["auto-queue-runs"] is True
    assert attrs["speculative"] is True


@pytest.mark.asyncio
@respx.mock
async def test_run_lifecycle_endpoints(client: TFEClient) -> None:
    create = respx.post(f"{BASE_URL}/runs").mock(return_value=httpx.Response(201, json={"data": {"id": "run-1"}}))
    get_run = respx.get(f"{BASE_URL}/runs/run-1").mock(return_value=httpx.Response(200, json={"data": {"id": "run-1"}}))
    get_plan = respx.get(f"{BASE_URL}/plans/plan-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "plan-1"}})
    )
    apply = respx.post(f"{BASE_URL}/runs/run-1/actions/apply").mock(return_value=httpx.Response(204))
    discard = respx.post(f"{BASE_URL}/runs/run-1/actions/discard").mock(return_value=httpx.Response(204))
    cancel = respx.post(f"{BASE_URL}/runs/run-1/actions/cancel").mock(return_value=httpx.Response(204))
    force = respx.post(f"{BASE_URL}/runs/run-1/actions/force-cancel").mock(return_value=httpx.Response(204))
    comment = respx.post(f"{BASE_URL}/runs/run-1/comments").mock(
        return_value=httpx.Response(201, json={"data": {"id": "c-1"}})
    )
    listing = respx.get(f"{BASE_URL}/workspaces/ws-1/runs").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "run-1"}]})
    )

    await client.create_run({"message": "go"}, "ws-1", configuration_version_id="cv-1")
    await client.get_run("run-1")
    await client.get_plan("plan-1")
    await client.apply_run("run-1", comment="ok")
    await client.discard_run("run-1")
    await client.cancel_run("run-1", comment="stop")
    await client.force_cancel_run("run-1")
    await client.add_run_comment("run-1", "note")
    await client.list_runs("ws-1", status="planned")

    body = json.loads(create.calls[0].request.content)["data"]
    assert body["relationships"]["configuration-version"]["data"]["id"] == "cv-1"
    assert get_run.called
    assert get_plan.called
    assert apply.called
    assert discard.called
    assert cancel.called
    assert force.called
    assert comment.called
    assert listing.called
    assert listing.calls[0].request.url.params["filter[status]"] == "planned"


@pytest.mark.asyncio
@respx.mock
async def test_link_vcs_and_project_endpoints(client: TFEClient) -> None:
    patch_ws = respx.patch(f"{BASE_URL}/workspaces/ws-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "ws-1"}})
    )
    create_prj = respx.post(f"{BASE_URL}/organizations/acme/projects").mock(
        return_value=httpx.Response(201, json={"data": {"id": "prj-1"}})
    )
    list_prj = respx.get(f"{BASE_URL}/organizations/acme/projects").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "prj-1"}]})
    )
    get_prj = respx.get(f"{BASE_URL}/projects/prj-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "prj-1"}})
    )
    teams = respx.get(f"{BASE_URL}/team-projects").mock(return_value=httpx.Response(200, json={"data": []}))
    update_prj = respx.patch(f"{BASE_URL}/projects/prj-1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "prj-1"}})
    )
    delete_prj = respx.delete(f"{BASE_URL}/projects/prj-1").mock(return_value=httpx.Response(204))
    assign = respx.post(f"{BASE_URL}/team-projects").mock(
        return_value=httpx.Response(201, json={"data": {"id": "tp-1"}})
    )

    await client.link_vcs_to_workspace(
        "ws-1",
        identifier="org/repo",
        branch="main",
        github_app_installation_id="ghain-1",
    )
    await client.create_project("p", description="d")
    await client.list_projects()
    await client.get_project("prj-1")
    await client.list_project_teams("prj-1")
    await client.update_project("prj-1", {"name": "p2"})
    await client.delete_project("prj-1")
    await client.move_workspace_to_project("ws-1", None)
    await client.assign_team_permissions("prj-1", "team-1", "write")

    vcs = json.loads(patch_ws.calls[0].request.content)["data"]["attributes"]["vcs-repo"]
    assert vcs["github-app-installation-id"] == "ghain-1"
    assert create_prj.called
    assert list_prj.called
    assert get_prj.called
    assert teams.called
    assert update_prj.called
    assert delete_prj.called
    assert assign.called
    move_body = json.loads(patch_ws.calls[1].request.content)["data"]["relationships"]["project"]
    assert move_body == {"data": None}


@pytest.mark.asyncio
@respx.mock
async def test_read_retries_retryable_http_then_succeeds(client: TFEClient) -> None:
    route = respx.get(f"{BASE_URL}/runs/run-1").mock(
        side_effect=[
            httpx.Response(429, json={"errors": [{"title": "Slow down"}]}),
            httpx.Response(200, json={"data": {"id": "run-1"}}),
        ]
    )
    result = await client.get_run("run-1")
    assert result["data"]["id"] == "run-1"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_mutating_network_error_is_outcome_unknown(client: TFEClient) -> None:
    respx.post(f"{BASE_URL}/runs").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(TFEError) as exc_info:
        await client.create_run({"message": "x"}, "ws-1")
    assert exc_info.value.error_code == TFEErrorCode.OUTCOME_UNKNOWN


@pytest.mark.asyncio
@respx.mock
async def test_read_network_error_exhausted_is_unreachable(client: TFEClient) -> None:
    respx.get(f"{BASE_URL}/runs/run-1").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(TFEError) as exc_info:
        await client.get_run("run-1")
    assert exc_info.value.error_code == TFEErrorCode.UNREACHABLE
    assert "unreachable" in exc_info.value.message


@pytest.mark.asyncio
@respx.mock
async def test_read_timeout_exhausted_is_unreachable(client: TFEClient) -> None:
    respx.get(f"{BASE_URL}/runs/run-1").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(TFEError) as exc_info:
        await client.get_run("run-1")
    assert exc_info.value.error_code == TFEErrorCode.UNREACHABLE
    assert "timed out" in exc_info.value.message


@pytest.mark.asyncio
@respx.mock
async def test_json_all_pages_returns_non_list_payload_as_is(client: TFEClient) -> None:
    respx.get(f"{BASE_URL}/organizations/acme/workspaces").mock(
        return_value=httpx.Response(200, json={"data": {"id": "single"}})
    )
    result = await client.list_workspaces()
    assert result == {"data": {"id": "single"}}


@pytest.mark.asyncio
@respx.mock
async def test_request_with_content_type_override(client: TFEClient) -> None:
    route = respx.put(f"{BASE_URL}/uploads/u-1").mock(return_value=httpx.Response(204))
    await client._request(
        "PUT",
        "/uploads/u-1",
        content=b"bytes",
        content_type="application/octet-stream",
        mutating=True,
    )
    assert route.calls[0].request.headers["Content-Type"] == "application/octet-stream"


@pytest.mark.asyncio
@respx.mock
async def test_upload_configuration_version_omits_authorization(client: TFEClient) -> None:
    upload_url = "https://uploads.example.com/config?X-Amz-Signature=abc"
    route = respx.put(upload_url).mock(return_value=httpx.Response(200))
    with patch(
        "syntara.terraform.client.validate_url_no_ssrf",
    ) as mock_validate:
        await client.upload_configuration_version(upload_url, b"archive-bytes")
    mock_validate.assert_called_once()
    assert route.called
    request = route.calls[0].request
    assert "Authorization" not in request.headers
    assert request.headers["Content-Type"] == "application/octet-stream"
    assert request.content == b"archive-bytes"


@pytest.mark.asyncio
async def test_upload_configuration_version_rejects_unsafe_url(client: TFEClient) -> None:
    with (
        patch(
            "syntara.terraform.client.validate_url_no_ssrf",
            side_effect=ValueError("URL resolves to a private IP address"),
        ),
        pytest.raises(TFEError) as exc_info,
    ):
        await client.upload_configuration_version("http://169.254.169.254/latest/meta-data/", b"x")
    assert exc_info.value.error_code == TFEErrorCode.VALIDATION
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_upload_configuration_version_network_error_is_outcome_unknown(client: TFEClient) -> None:
    upload_url = "https://uploads.example.com/config"
    respx.put(upload_url).mock(side_effect=httpx.ConnectError("down"))
    with (
        patch("syntara.terraform.client.validate_url_no_ssrf"),
        pytest.raises(TFEError) as exc_info,
    ):
        await client.upload_configuration_version(upload_url, b"x")
    assert exc_info.value.error_code == TFEErrorCode.OUTCOME_UNKNOWN


@pytest.mark.asyncio
@respx.mock
async def test_upload_configuration_version_maps_http_errors(client: TFEClient) -> None:
    upload_url = "https://uploads.example.com/config"
    respx.put(upload_url).mock(return_value=httpx.Response(403, json={"errors": [{"title": "Denied"}]}))
    with (
        patch("syntara.terraform.client.validate_url_no_ssrf"),
        pytest.raises(TFEError) as exc_info,
    ):
        await client.upload_configuration_version(upload_url, b"x")
    assert exc_info.value.error_code == TFEErrorCode.AUTHZ_FAILED


@pytest.mark.asyncio
@respx.mock
async def test_json_returns_empty_dict_for_204(client: TFEClient) -> None:
    respx.post(f"{BASE_URL}/runs/run-1/actions/apply").mock(return_value=httpx.Response(204))
    result: dict[str, Any] = await client._json("POST", "/runs/run-1/actions/apply", mutating=True)
    assert result == {}
