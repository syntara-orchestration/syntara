"""Shared helpers for workflow tests."""

from typing import Any


def create_minimal_workflow_definition(
    name: str = "test-workflow",
    description: str = "Test workflow description",
    activity_id: str = "test_activity",
    activity_type: str = "script_python",
) -> dict[str, Any]:
    """Create a minimal valid V2 workflow definition for testing.

    Returns a dict matching the V2 workflow definition schema with
    schema_version, triggers, nodes, and edges.

    Args:
        name: Workflow name
        description: Workflow description
        activity_id: Activity ID for the node
        activity_type: V2 node type (script_python, script_bash, http_request, agentic, aap_job_template,
                       condition, loop, converge, approval)

    Returns:
        Dict with V2 workflow definition structure ready for validation

    """
    trigger_id = "trigger_manual"
    node: dict[str, Any] = {
        "id": activity_id,
        "name": f"Activity {activity_id}",
        "type": activity_type,
    }

    if activity_type in {"script_python", "script_bash"}:
        code = "echo hello" if activity_type == "script_bash" else "print('hello')"
        node["parameters"] = {"code": code}
    elif "parameters" not in node:
        node["parameters"] = {}

    return {
        "schema_version": "2.0.0",
        "name": name,
        "description": description,
        "triggers": [{"id": trigger_id, "type": "manual_trigger", "parameters": {}}],
        "nodes": [node],
        "edges": [{"from": trigger_id, "to": activity_id}],
    }


def create_workflow_definition_with_activities(
    name: str,
    description: str,
    activities: list[dict[str, object]],
) -> dict[str, Any]:
    """Create a V2 workflow definition with custom activities as nodes.

    Args:
        name: Workflow name
        description: Workflow description
        activities: List of activity/node definitions

    Returns:
        Dict with V2 workflow definition structure

    """
    trigger_id = "trigger_manual"
    edges: list[dict[str, str]] = [{"from": trigger_id, "to": str(activities[0]["id"])}] if activities else []
    # Chain activities sequentially
    for i in range(len(activities) - 1):
        edges.append({"from": str(activities[i]["id"]), "to": str(activities[i + 1]["id"])})

    return {
        "schema_version": "2.0.0",
        "name": name,
        "description": description,
        "triggers": [{"id": trigger_id, "type": "manual_trigger", "parameters": {}}],
        "nodes": activities,
        "edges": edges,
    }
