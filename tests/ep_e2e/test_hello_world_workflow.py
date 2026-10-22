"""Cold-start hello-world workflow through the AO API.

Replaces docs/feature-branch-assets/run-hello-world-demo.sh for the Konflux
Kind pipeline: create a script-node workflow, start an execution, and wait
until AO reports it completed via Execution Plane dispatch.

AO completion alone is not enough: a Temporal worker can run the script
in-process and still report completed. The test therefore also reads the
matching work item from the Execution Plane API and requires that EP's
stored result contains the unique hello-world marker.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e]

_SCRIPT_NODE_ID = "script_node"


def _hello_world_definition(name: str, marker: str) -> dict[str, Any]:
    return {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": _SCRIPT_NODE_ID,
                "name": "Hello Script",
                "type": "script",
                "parameters": {"code": f"echo 'hello world {marker}'", "language": "bash"},
            }
        ],
        "edges": [{"from": "trigger", "to": "script_node"}],
    }


def _activity_by_id(execution: dict[str, Any], activity_id: str) -> dict[str, Any] | None:
    activities = execution.get("activities")
    if not isinstance(activities, list):
        return None
    for activity in activities:
        if isinstance(activity, dict) and activity.get("activity_id") == activity_id:
            return activity
    return None


def _activity_stdout(activity: dict[str, Any]) -> str:
    output = activity.get("output_data")
    if not isinstance(output, dict):
        return ""
    stdout = output.get("stdout")
    if isinstance(stdout, str):
        return stdout
    nested = output.get("output")
    if isinstance(nested, dict) and isinstance(nested.get("stdout"), str):
        return str(nested["stdout"])
    return ""


def _blob(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, default=str)


def _script_work_item_id(activities: list[dict[str, Any]]) -> str | None:
    for activity in activities:
        name = activity.get("activity_name") or activity.get("activity_id")
        work_item_id = activity.get("id")
        if name == _SCRIPT_NODE_ID and work_item_id:
            return str(work_item_id)
    return None


def _work_item_from_ep(ep_client, ao_client, execution_id: str, marker: str) -> dict[str, Any]:
    """Return the EP work item that produced ``marker``, or fail if Temporal ran it."""
    temporal_bypass = (
        "AO completed hello-world but Execution Plane has no matching work item; "
        "the script completed in Temporal, not on EP"
    )
    work_item_id = _script_work_item_id(ao_client.list_activities(execution_id))
    if work_item_id:
        item = ep_client.get_work_item(work_item_id)
        if item is not None:
            return item
    scanned = _scan_ep_for_marker(ep_client, marker)
    assert scanned is not None, temporal_bypass
    return scanned


def _scan_ep_for_marker(ep_client, marker: str) -> dict[str, Any] | None:
    for summary in ep_client.list_work_items(status="completed"):
        work_item_id = summary.get("id")
        if not work_item_id:
            continue
        item = ep_client.get_work_item(str(work_item_id))
        if item is not None and marker in _blob(item.get("result")):
            return item
    return None


def test_admin_can_list_a_project(ao_client) -> None:
    project_id = ao_client.default_project_id()
    assert project_id


def test_hello_world_script_workflow_completes(ao_client, ep_client) -> None:
    marker = uuid.uuid4().hex
    expected = f"hello world {marker}"
    name = f"hello-world-e2e-{marker[:8]}"
    workflow = ao_client.create_workflow(
        {
            "name": name,
            "description": "Cold-start EP: single script node echoing hello world",
            "project_id": ao_client.default_project_id(),
            "workflow_definition": _hello_world_definition(name, marker),
        }
    )
    execution = ao_client.create_execution(str(workflow["id"]))
    execution_id = str(execution["id"])
    completed = ao_client.poll_execution(execution_id)

    script = _activity_by_id(completed, _SCRIPT_NODE_ID)
    assert script is not None, f"script_node activity missing from execution {execution_id}"
    assert script.get("status") == "completed", (
        f"script_node status={script.get('status')!r} error_details={script.get('error_details')!r}"
    )
    stdout = _activity_stdout(script)
    assert expected in stdout, f"AO script_node stdout missing {expected!r}: {stdout!r}"

    work_item = _work_item_from_ep(ep_client, ao_client, execution_id, marker)
    assert work_item.get("status") == "completed", (
        f"EP work item status={work_item.get('status')!r} result={work_item.get('result')!r}"
    )
    assert work_item.get("claimed_at"), f"EP work item {work_item.get('id')} was never claimed by a worker"
    assert work_item.get("completed_at"), f"EP work item {work_item.get('id')} has no completed_at"
    assert expected in _blob(work_item.get("result")), (
        f"EP work item {work_item.get('id')} result does not contain {expected!r}: {work_item.get('result')!r}"
    )
