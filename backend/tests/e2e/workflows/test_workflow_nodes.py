"""End-to-end tests for v2 workflow node types.

Tests script, http_request, condition, loop, converge, and switch nodes
using the full Nexus stack (API, Temporal worker, containers).

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

from typing import Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_definition import WorkflowDefinition

AGENTIC_POLL_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Script node
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_script_node_bash(syntara_api: SyntaraApiRegistry):
    """A bash script node executes and the workflow completes."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-script-bash",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "hello_script",
                    "name": "Hello Script",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "Hello from E2E test"',
                    },
                },
            ],
            "edges": [{"from": "trigger", "to": "hello_script"}],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["trigger"] == "completed"
    assert activities["hello_script"] == "completed"


@pytest.mark.e2e
def test_script_node_python(syntara_api: SyntaraApiRegistry):
    """A python script node executes and the workflow completes."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-script-python",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "py_script",
                    "name": "Python Script",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "import json; print(json.dumps({'result': 2 + 2}))",
                    },
                },
            ],
            "edges": [{"from": "trigger", "to": "py_script"}],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["py_script"] == "completed"


# ---------------------------------------------------------------------------
# HTTP request node
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_http_request_node(syntara_api: SyntaraApiRegistry):
    """An HTTP request node calls an endpoint and the workflow completes.

    Note: targets an external URL because SSRF mitigation (AAP-79016) blocks
    private IPs until the allowlist for worker_base_url is propagated by the
    Operator. Revert to worker_base_url/health once the allowlist is confirmed
    working in CI.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-http-request",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "health_check",
                    "name": "Health Check",
                    "type": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": "https://example.com",
                    },
                },
            ],
            "edges": [{"from": "trigger", "to": "health_check"}],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["health_check"] == "completed"


# ---------------------------------------------------------------------------
# Condition node
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_condition_true_branch(syntara_api: SyntaraApiRegistry):
    """A condition that evaluates to true routes to the true branch only."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-condition-true",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "check",
                    "name": "Check Condition",
                    "type": "condition",
                    "parameters": {"condition": "1 == 1"},
                },
                {
                    "id": "true_branch",
                    "name": "True Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "condition was true"'},
                },
                {
                    "id": "false_branch",
                    "name": "False Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "condition was false"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "check"},
                {"from": "check", "to": "true_branch", "from_port": "true"},
                {"from": "check", "to": "false_branch", "from_port": "false"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["check"].status == "completed"
    assert activities["true_branch"].status == "completed"
    if "false_branch" in activities:
        assert activities["false_branch"].status != "completed", "False branch should not have run"


@pytest.mark.e2e
def test_condition_false_branch(syntara_api: SyntaraApiRegistry):
    """A condition that evaluates to false routes to the false branch only."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-condition-false",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "check",
                    "name": "Check Condition",
                    "type": "condition",
                    "parameters": {"condition": "1 == 0"},
                },
                {
                    "id": "true_branch",
                    "name": "True Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "should not run"'},
                },
                {
                    "id": "false_branch",
                    "name": "False Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "condition was false"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "check"},
                {"from": "check", "to": "true_branch", "from_port": "true"},
                {"from": "check", "to": "false_branch", "from_port": "false"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["check"].status == "completed"
    assert activities["false_branch"].status == "completed"
    if "true_branch" in activities:
        assert activities["true_branch"].status != "completed", "True branch should not have run"


# ---------------------------------------------------------------------------
# Loop node
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_loop_for_each(syntara_api: SyntaraApiRegistry):
    """A for_each loop iterates over items and executes the body for each."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-loop-foreach",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "loop",
                    "name": "Loop Over Items",
                    "type": "loop",
                    "parameters": {
                        "type": "for_each",
                        "items": '["alpha", "bravo", "charlie"]',
                    },
                },
                {
                    "id": "loop_body",
                    "name": "Loop Body",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Processing item"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "loop"},
                {"from": "loop", "to": "loop_body", "from_port": "iterate"},
                {"from": "loop_body", "to": "loop", "to_port": "iterate"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["loop"] == "completed"
    assert activities["loop_body"] == "completed"


# ---------------------------------------------------------------------------
# Converge node (parallel paths)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_parallel_paths_with_converge(syntara_api: SyntaraApiRegistry):
    """Two parallel script nodes converge before a final node executes."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-parallel-converge",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "path_a",
                    "name": "Path A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Path A done"'},
                },
                {
                    "id": "path_b",
                    "name": "Path B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Path B done"'},
                },
                {
                    "id": "join",
                    "name": "Join Paths",
                    "type": "converge",
                    "parameters": {},
                },
                {
                    "id": "final_step",
                    "name": "Final Step",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "All paths completed"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "path_a"},
                {"from": "trigger", "to": "path_b"},
                {"from": "path_a", "to": "join"},
                {"from": "path_b", "to": "join"},
                {"from": "join", "to": "final_step"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["path_a"] == "completed"
    assert activities["path_b"] == "completed"
    assert activities["join"] == "completed"
    assert activities["final_step"] == "completed"


# ---------------------------------------------------------------------------
# Combined: script -> condition -> parallel -> converge
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_multi_node_workflow(syntara_api: SyntaraApiRegistry):
    """A workflow combining script, condition, parallel paths, and converge."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-multi-node",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "setup",
                    "name": "Setup",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "setup done"'},
                },
                {
                    "id": "gate",
                    "name": "Gate",
                    "type": "condition",
                    "parameters": {"condition": "True"},
                },
                {
                    "id": "task_a",
                    "name": "Task A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "task a"'},
                },
                {
                    "id": "task_b",
                    "name": "Task B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "task b"'},
                },
                {
                    "id": "join",
                    "name": "Join",
                    "type": "converge",
                    "parameters": {},
                },
                {
                    "id": "finish",
                    "name": "Finish",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "done"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "setup"},
                {"from": "setup", "to": "gate"},
                # condition true -> two parallel tasks
                {"from": "gate", "to": "task_a", "from_port": "true"},
                {"from": "gate", "to": "task_b", "from_port": "true"},
                {"from": "task_a", "to": "join"},
                {"from": "task_b", "to": "join"},
                {"from": "join", "to": "finish"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["setup"] == "completed"
    assert activities["gate"] == "completed"
    assert activities["task_a"] == "completed"
    assert activities["task_b"] == "completed"
    assert activities["join"] == "completed"
    assert activities["finish"] == "completed"


# ---------------------------------------------------------------------------
# Cross-node combinations with agentic
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.xfail(strict=False, reason="OpenRouter insufficient credits")
def test_script_then_agentic(
    syntara_api: SyntaraApiRegistry,
    llm_credential_id: str,
    llm_model_id: str,
    first_project_id: UUID,
):
    """A script node feeds into an agentic node."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-script-to-agentic",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "prep",
                    "name": "Prep Data",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "jimmy"',
                    },
                },
                {
                    "id": "agent",
                    "name": "Greet via Agent",
                    "type": "agentic",
                    "parameters": {
                        "prompt": "Say hello in one sentence.",
                        "credential_id": llm_credential_id,
                        "llm_model_id": llm_model_id,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "prep"},
                {"from": "prep", "to": "agent"},
            ],
        },
        timeout=AGENTIC_POLL_TIMEOUT,
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["prep"] == "completed"
    assert activities["agent"] == "completed"


@pytest.mark.e2e
@pytest.mark.xfail(strict=False, reason="OpenRouter insufficient credits")
def test_agentic_then_script(
    syntara_api: SyntaraApiRegistry,
    llm_credential_id: str,
    llm_model_id: str,
    first_project_id: UUID,
):
    """An agentic node feeds into a script node."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-agentic-to-script",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "agent",
                    "name": "Agent Task",
                    "type": "agentic",
                    "parameters": {
                        "prompt": "Say hello in one sentence.",
                        "credential_id": llm_credential_id,
                        "llm_model_id": llm_model_id,
                    },
                },
                {
                    "id": "post_process",
                    "name": "Post Process",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "Agent task finished, post-processing complete"',
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "agent"},
                {"from": "agent", "to": "post_process"},
            ],
        },
        timeout=AGENTIC_POLL_TIMEOUT,
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["agent"] == "completed"
    assert activities["post_process"] == "completed"


@pytest.mark.e2e
@pytest.mark.xfail(strict=False, reason="OpenRouter insufficient credits")
def test_loop_with_agentic_body(
    syntara_api: SyntaraApiRegistry,
    llm_credential_id: str,
    llm_model_id: str,
    first_project_id: UUID,
):
    """A loop iterates with an agentic node as the loop body."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-loop-agentic",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "loop",
                    "name": "Loop Over Names",
                    "type": "loop",
                    "parameters": {
                        "type": "for_each",
                        "items": '["jimmy", "sarah"]',
                    },
                },
                {
                    "id": "greet",
                    "name": "Greet Person",
                    "type": "agentic",
                    "parameters": {
                        "prompt": "Say hello in one sentence.",
                        "credential_id": llm_credential_id,
                        "llm_model_id": llm_model_id,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "loop"},
                {"from": "loop", "to": "greet", "from_port": "iterate"},
                {"from": "greet", "to": "loop", "to_port": "iterate"},
            ],
        },
        timeout=AGENTIC_POLL_TIMEOUT,
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["loop"] == "completed"
    assert activities["greet"] == "completed"


@pytest.mark.e2e
@pytest.mark.xfail(strict=False, reason="OpenRouter insufficient credits")
def test_http_request_then_agentic(
    syntara_api: SyntaraApiRegistry, llm_credential_id: str, llm_model_id: str, first_project_id: UUID
):
    """An HTTP request node feeds into an agentic node.

    Note: targets an external URL because SSRF mitigation (AAP-79016) blocks
    private IPs until the allowlist for worker_base_url is propagated by the
    Operator. Revert to worker_base_url/health once the allowlist is confirmed
    working in CI.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-http-to-agentic",
        {
            "name": "nodes",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "fetch",
                    "name": "Fetch Page",
                    "type": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": "https://example.com",
                    },
                },
                {
                    "id": "analyze",
                    "name": "Analyze Response",
                    "type": "agentic",
                    "parameters": {
                        "prompt": "Say 'Health check passed' in one sentence.",
                        "credential_id": llm_credential_id,
                        "llm_model_id": llm_model_id,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "fetch"},
                {"from": "fetch", "to": "analyze"},
            ],
        },
        timeout=AGENTIC_POLL_TIMEOUT,
        project_id=first_project_id,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["fetch"] == "completed"
    assert activities["analyze"] == "completed"


# ---------------------------------------------------------------------------
# Switch node
# ---------------------------------------------------------------------------


def _switch_workflow_definition(cases: list[dict[str, str]], default_port: str = "default") -> dict[str, Any]:
    """Build a switch workflow definition with downstream script nodes per case + default."""
    nodes: list[dict[str, Any]] = [
        {
            "id": "sw",
            "name": "Switch Router",
            "type": "switch",
            "parameters": {"cases": cases, "default_port": default_port},
        },
    ]
    edges: list[dict[str, Any]] = [{"from": "trigger", "to": "sw"}]

    for case in cases:
        port = case["port"]
        node_id = f"action_{port}"
        nodes.append(
            {
                "id": node_id,
                "name": f"Action {port}",
                "type": "script",
                "parameters": {"language": "bash", "code": f'echo "{port} executed"'},
            }
        )
        edges.append({"from": "sw", "to": node_id, "from_port": port})

    nodes.append(
        {
            "id": "action_default",
            "name": "Default Action",
            "type": "script",
            "parameters": {"language": "bash", "code": 'echo "default executed"'},
        }
    )
    edges.append({"from": "sw", "to": "action_default", "from_port": default_port})

    return {
        "name": "test",
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": edges,
    }


@pytest.mark.e2e
def test_switch_first_case_matches(syntara_api: SyntaraApiRegistry):
    """Switch routes to first matching case, other cases and default are skipped."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-first-case",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "Always True", "condition": "1 == 1"},
                {"port": "case_1", "label": "Also True", "condition": "2 == 2"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["sw"].status == "completed"
    assert activities["action_case_0"].status == "completed"
    assert activities["action_case_1"].status == "skipped"
    assert activities["action_default"].status == "skipped"

    # Verify switch node output contains matched port
    sw_output = activities["sw"].output_data
    if sw_output is not None:
        output_dict = sw_output if isinstance(sw_output, dict) else getattr(sw_output, "additional_properties", {})
        assert output_dict.get("matched_port") == "case_0"


@pytest.mark.e2e
def test_switch_second_case_matches(syntara_api: SyntaraApiRegistry):
    """Switch skips first case (false), routes to second case (true)."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-second-case",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "False", "condition": "1 == 0"},
                {"port": "case_1", "label": "True", "condition": "1 == 1"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["sw"].status == "completed"
    assert activities["action_case_1"].status == "completed"
    assert activities["action_case_0"].status == "skipped"
    assert activities["action_default"].status == "skipped"


@pytest.mark.e2e
def test_switch_default_fallback(syntara_api: SyntaraApiRegistry):
    """Switch routes to default when no case matches."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-default",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "False", "condition": "1 == 0"},
                {"port": "case_1", "label": "Also False", "condition": "2 == 0"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["sw"].status == "completed"
    assert activities["action_default"].status == "completed"
    assert activities["action_case_0"].status == "skipped"
    assert activities["action_case_1"].status == "skipped"


@pytest.mark.e2e
def test_switch_3_case_routing(syntara_api: SyntaraApiRegistry):
    """Switch with 3 cases routes to the first matching case; later cases and default are skipped."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-3-case",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "False A", "condition": "1 == 0"},
                {"port": "case_1", "label": "True B", "condition": "1 == 1"},
                {"port": "case_2", "label": "Also True C", "condition": "2 == 2"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["sw"].status == "completed"
    assert activities["action_case_1"].status == "completed"
    assert activities["action_case_0"].status == "skipped"
    assert activities["action_case_2"].status == "skipped"
    assert activities["action_default"].status == "skipped"


@pytest.mark.e2e
def test_switch_single_case_with_default(syntara_api: SyntaraApiRegistry):
    """Switch with one case + default works correctly."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-single-case",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "Only Case", "condition": "1 == 1"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["sw"].status == "completed"
    assert activities["action_case_0"].status == "completed"
    assert activities["action_default"].status == "skipped"


@pytest.mark.e2e
def test_switch_numeric_comparison(syntara_api: SyntaraApiRegistry):
    """Switch evaluates numeric comparison operators correctly."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-numeric",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "Greater", "condition": "10 > 5"},
                {"port": "case_1", "label": "Less", "condition": "10 < 5"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["action_case_0"].status == "completed"
    assert activities["action_case_1"].status == "skipped"
    assert activities["action_default"].status == "skipped"


@pytest.mark.e2e
def test_switch_negation(syntara_api: SyntaraApiRegistry):
    """Switch evaluates not() expressions correctly."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-negation",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "Not False", "condition": "not False"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["action_case_0"].status == "completed"
    assert activities["action_default"].status == "skipped"


@pytest.mark.e2e
def test_switch_skipped_branches_have_activity_records(syntara_api: SyntaraApiRegistry):
    """Skipped branches have ActivityExecution records with correct status and null timing."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-skipped",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "True", "condition": "1 == 1"},
                {"port": "case_1", "label": "False", "condition": "1 == 0"},
                {"port": "case_2", "label": "Also False", "condition": "2 == 0"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}

    # Taken branch has completed status and timing data
    assert activities["action_case_0"].status == "completed"
    assert activities["action_case_0"].started_at is not None
    assert activities["action_case_0"].completed_at is not None

    # Skipped branches have records with skipped status and were never started
    for skipped_id in ("action_case_1", "action_case_2", "action_default"):
        assert activities[skipped_id].status == "skipped"
        assert activities[skipped_id].started_at is None


@pytest.mark.e2e
def test_switch_in_operator(syntara_api: SyntaraApiRegistry):
    """Switch evaluates 'in' operator correctly."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-in-operator",
        _switch_workflow_definition(
            [
                {"port": "case_0", "label": "Contains a", "condition": "'a' in 'abc'"},
                {"port": "case_1", "label": "Contains z", "condition": "'z' in 'abc'"},
            ]
        ),
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["action_case_0"].status == "completed"
    assert activities["action_case_1"].status == "skipped"
    assert activities["action_default"].status == "skipped"


@pytest.mark.e2e
def test_switch_empty_cases_saves_with_validation_issues(syntara_api: SyntaraApiRegistry, first_project_id: UUID):
    """Switch with empty cases array saves with validation issues."""
    wf_def = WorkflowDefinition.from_dict(
        {
            "name": "test",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "sw",
                    "name": "Empty Switch",
                    "type": "switch",
                    "parameters": {"cases": [], "default_port": "default"},
                },
                {
                    "id": "action_default",
                    "name": "Default",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "should not run"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "sw"},
                {"from": "sw", "to": "action_default", "from_port": "default"},
            ],
        },
    )
    response = syntara_api.workflows.create(
        body=WorkflowCreate(
            name="e2e-switch-empty-cases",
            description="E2E test: empty switch cases",
            workflow_definition=wf_def,
            project_id=first_project_id,
        )
    )
    assert response.is_success, f"Save should succeed: {response.status_code}"
    assert response.parsed is not None
    assert response.parsed.has_validation_issues is True


@pytest.mark.e2e
def test_switch_after_script_node(syntara_api: SyntaraApiRegistry):
    """Switch reads upstream node output via namespace injection."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-switch-after-script",
        {
            "name": "test",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "setup",
                    "name": "Setup",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": 'import json; print(json.dumps({"priority": "high"}))',
                    },
                },
                {
                    "id": "sw",
                    "name": "Route by Priority",
                    "type": "switch",
                    "parameters": {
                        "cases": [
                            {"port": "case_0", "label": "High", "condition": "${setup.stdout_json.priority} == 'high'"},
                            {"port": "case_1", "label": "Low", "condition": "${setup.stdout_json.priority} == 'low'"},
                        ],
                        "default_port": "default",
                    },
                },
                {
                    "id": "action_high",
                    "name": "High Priority",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "high priority"'},
                },
                {
                    "id": "action_low",
                    "name": "Low Priority",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "low priority"'},
                },
                {
                    "id": "action_default",
                    "name": "Default",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "default"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "setup"},
                {"from": "setup", "to": "sw"},
                {"from": "sw", "to": "action_high", "from_port": "case_0"},
                {"from": "sw", "to": "action_low", "from_port": "case_1"},
                {"from": "sw", "to": "action_default", "from_port": "default"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["setup"].status == "completed"
    assert activities["sw"].status == "completed"
    assert activities["action_high"].status == "completed"
    assert activities["action_low"].status == "skipped"
    assert activities["action_default"].status == "skipped"
