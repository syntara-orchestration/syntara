"""Live HTTP acceptance against a configured public httpbin-compatible fixture.

Require both AO and EP evidence; never count a native request as an EP success.
The fixture endpoint must be owned by the test operator and allow delayed requests.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4, uuid5

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.e2e.execution_plane.conftest import AoClient, EpClient

pytestmark = pytest.mark.e2e
_NODE_ID = "http_acceptance"
_TERMINAL = {"completed", "failed", "cancelled", "completed_with_errors"}


@pytest.fixture
def http_fixture() -> tuple[str, str]:
    base = os.environ.get("E2E_HTTP_BASE_URL")
    target = os.environ.get("E2E_HTTP_TARGET_ID")
    if not base or not target:
        pytest.skip("Set E2E_HTTP_BASE_URL and E2E_HTTP_TARGET_ID for live HTTP EP acceptance")
    assert base.startswith("https://"), "Use an operator-owned public HTTPS httpbin-compatible endpoint"
    return base.rstrip("/"), str(UUID(target))


@pytest.fixture
def http_workflows(ao_client: AoClient) -> Iterator[list[tuple[str, str | None]]]:
    created: list[tuple[str, str | None]] = []
    try:
        yield created
    finally:
        for workflow_id, execution_id in reversed(created):
            if execution_id and ao_client.get_execution(execution_id).get("status") not in _TERMINAL:
                ao_client.cancel_execution(execution_id)
                _wait_terminal(ao_client, execution_id)
            ao_client.delete_workflow(workflow_id)


def _start(
    ao: AoClient,
    workflows: list[tuple[str, str | None]],
    fixture: tuple[str, str],
    path: str,
    *,
    use_ep: bool = True,
    timeout: int = 60,
) -> tuple[str, str]:
    base, target = fixture
    marker = uuid4().hex
    parameters: dict[str, Any] = {"method": "GET", "url": base + path, "query_params": {"marker": marker}}
    if use_ep:
        parameters["execution_profile"] = {"type": "execution_target", "execution_target_id": target}
    name = f"http-acceptance-{marker[:8]}"
    definition = {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": _NODE_ID,
                "type": "http_request",
                "parameters": parameters,
                "settings": {"timeout": timeout, "retry_policy": {"max_retries": 0}},
            }
        ],
        "edges": [{"from": "trigger", "to": _NODE_ID}],
    }
    workflow = ao.create_workflow(
        {"name": name, "project_id": ao.default_project_id(), "workflow_definition": definition}
    )
    workflow_id = str(workflow["id"])
    workflows.append((workflow_id, None))
    execution = ao.create_execution(workflow_id)
    execution_id = str(execution["id"])
    workflows[-1] = (workflow_id, execution_id)
    return execution_id, marker


def _wait_terminal(ao: AoClient, execution_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + float(os.environ.get("E2E_POLL_TIMEOUT", "180"))
    while time.monotonic() < deadline:
        execution = ao.get_execution(execution_id)
        if execution.get("status") in _TERMINAL:
            return execution
        time.sleep(1)
    ao.cancel_execution(execution_id)
    pytest.fail(f"HTTP execution {execution_id} did not reach a terminal state")


def _work(ep: EpClient, execution_id: str) -> dict[str, Any] | None:
    return ep.get_work_item(str(uuid5(UUID(execution_id), _NODE_ID)))


def _wait_work(ep: EpClient, execution_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + float(os.environ.get("E2E_POLL_TIMEOUT", "180"))
    while time.monotonic() < deadline:
        item = _work(ep, execution_id)
        if item is not None and item.get("status") in statuses:
            return item
        time.sleep(1)
    pytest.fail(f"HTTP work for {execution_id} did not reach {sorted(statuses)}")


@pytest.mark.parametrize("use_ep", [False, True], ids=["native-default", "explicit-ep"])
def test_http_success_proves_selected_executor(ao_client, ep_client, http_fixture, http_workflows, *, use_ep: bool):
    execution_id, marker = _start(ao_client, http_workflows, http_fixture, "/get", use_ep=use_ep)
    execution = _wait_terminal(ao_client, execution_id)
    assert execution["status"] == "completed", execution.get("error_details")
    activities = ao_client.list_activities(execution_id)
    activity = next(a for a in activities if (a.get("activity_name") or a.get("activity_id")) == _NODE_ID)
    output = activity["output_data"]
    output = output.get("output", output)
    assert output["status_code"] == 200
    assert output["body"]["args"]["marker"] == marker
    if use_ep:
        item = _wait_work(ep_client, execution_id, {"completed"})
        assert item["claimed_at"]
        assert item["completed_at"]
        assert item["runtime_context"]["execution_id"] == execution_id
        placed = ep_client.list_work_items(work_item_id=str(item["id"]), execution_target_id=http_fixture[1])
        assert [str(row["id"]) for row in placed] == [str(item["id"])], "HTTP ran on an unexpected execution target"
        assert item["result"]["output"]["body"]["args"]["marker"] == marker
    else:
        assert _work(ep_client, execution_id) is None, "Native HTTP unexpectedly created EP work"


@pytest.mark.parametrize(
    ("path", "timeout"), [("/status/503", 60), ("/delay/10", 2)], ids=["upstream-error", "timeout"]
)
def test_http_ep_failure_reaches_ao(ao_client, ep_client, http_fixture, http_workflows, path, timeout):
    execution_id, _ = _start(ao_client, http_workflows, http_fixture, path, timeout=timeout)
    execution = _wait_terminal(ao_client, execution_id)
    assert execution["status"] in {"failed", "completed_with_errors"}
    item = _wait_work(ep_client, execution_id, {"failed", "cancelled"})
    assert item["runtime_context"]["execution_id"] == execution_id
    assert item["claimed_at"], "Failure happened before an EP worker claimed the HTTP request"


def test_http_cancellation_reaches_ep(ao_client, ep_client, http_fixture, http_workflows):
    execution_id, _ = _start(ao_client, http_workflows, http_fixture, "/delay/30", timeout=120)
    _wait_work(ep_client, execution_id, {"running"})
    ao_client.cancel_execution(execution_id)
    assert _wait_terminal(ao_client, execution_id)["status"] == "cancelled"
    item = _wait_work(ep_client, execution_id, {"cancelled"})
    assert item["cancellation_requested"] is True
