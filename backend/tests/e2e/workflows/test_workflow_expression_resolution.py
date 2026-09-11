"""E2E tests for Workflow Expression Resolution.

Tests that ${...} expressions in config fields (e.g., config.environment) referencing
upstream node outputs are resolved correctly during execution.

Expression resolution is implemented via _resolve_node_config() which resolves all
${...} expressions in config fields before the activity runs. For script nodes,
resolved values in config.environment are passed as environment variables to the script.

Test Plan Coverage:
- API-18 (Expression Resolution - Node Output References): FULLY COVERED
  - Tests ${node_id.stdout_json.field} expressions in config.environment
  - Tests ${trigger_id.field} expressions referencing trigger node outputs
- API-19 (Expression Resolution - System Variables): PARTIALLY COVERED
  - ${inputs.*} / ${input.*}: not a reserved namespace. Use ${trigger.*} /
    ${trigger_id.field} for trigger payload. A node whose id is ``input`` can
    still be referenced as ${input.*}.
  - ${execution.id}: Implemented but at a different path. The correct expression is
    ${workflow_context.execution.id}. Covered by test_workflow_context_execution_id_resolves.
  - ${workflow.vars.x}: NOT implemented — no namespace creation in the engine.
- API-20 (Expression Resolution - Unresolvable Expression Error): FULLY COVERED
  - Tests that referencing a nonexistent field fails the consuming node
  - Tests that the error message identifies the unresolvable path
  - Tests that continue_on_failure absorbs the resolution failure

"""

from typing import Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution_until_complete
from orchestrator_test_sdk.factories.workflows import WorkflowFactory
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionCreate,
    ExecutionCreateInputData,
    WorkflowDefinition,
)
from syntara_api_client.models.activity_status import ActivityStatus
from syntara_api_client.models.execution_status import ExecutionStatus

pytestmark = [pytest.mark.e2e]


def _workflow_definition_with_nodes(
    workflow_name: str,
    *nodes: dict[str, Any],
    edges: list[dict[str, Any]] | None = None,
) -> WorkflowDefinition:
    """Create a workflow definition with custom nodes and edges."""
    return WorkflowDefinition.from_dict(
        {
            "name": workflow_name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": list(nodes),
            "edges": edges or [],
        }
    )


class TestExpressionResolution:
    """Tests for ${...} expression resolution in workflow execution."""

    def test_node_output_reference_resolution(
        self,
        syntara_api: SyntaraApiRegistry,
        create_workflow: WorkflowFactory,
        first_project_id: UUID,
    ):
        """Test that ${node_id.field} expressions resolve to upstream node outputs.

        Objective: Verify that ${...} expressions referencing upstream node outputs
        are resolved correctly during execution via config.environment.

        Test Procedure:
        1. Create a workflow with:
           - Node A: Script node that produces structured JSON output
           - Node B: Script node with ${node_a.stdout_json.message} in config.environment
        2. Execute the workflow
        3. Verify Node B received the resolved value from Node A's output

        Expected Results:
        - Node A executes and produces output with structured data
        - The expression resolver substitutes ${node_a.stdout_json.message} with actual value
        - Node B's script receives the resolved value via environment variable
        """
        workflow_name = unique_name("e2e-expression-resolution")

        # Step 1: Create workflow with two connected nodes
        # Node A produces JSON output with a field "message"
        # Node B uses ${node_a.stdout_json.message} in config.environment to reference that field
        workflow_id, _ = create_workflow(
            api=syntara_api,
            project_id=first_project_id,
            name=workflow_name,
            definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "node_a",
                    "name": "Producer Node",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": 'print(\'{"message": "Hello from Node A", "status": "success", "count": 42}\')',
                    },
                },
                {
                    "id": "node_b",
                    "name": "Consumer Node",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "import os; msg = os.environ.get('MESSAGE', 'default'); print(f'Received: {msg}')",
                        "environment": {
                            "MESSAGE": "${node_a.stdout_json.message}",
                        },
                    },
                },
                edges=[
                    {"from": "trigger_manual", "to": "node_a"},
                    {"from": "node_a", "to": "node_b"},
                ],
            ),
        )

        # Step 2: Execute the workflow
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow_id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        execution_id = execution.id

        # Poll until execution completes
        final_execution = poll_execution_until_complete(syntara_api, execution_id)

        # Expected Result 1: Execution completes successfully
        assert final_execution.status == ExecutionStatus.COMPLETED, (
            f"Execution should complete successfully, got: {final_execution.status}"
        )

        # Expected Result 2: Both nodes executed successfully
        assert final_execution.activities is not None, "Execution should have activities"

        # Find node_a and node_b activities
        activities_by_id = {activity.activity_id: activity for activity in final_execution.activities}

        assert "node_a" in activities_by_id, "node_a activity should exist"
        assert "node_b" in activities_by_id, "node_b activity should exist"

        node_a_activity = activities_by_id["node_a"]
        node_b_activity = activities_by_id["node_b"]

        # Expected Result 3: Node A produced output
        assert node_a_activity.status == "completed", "node_a should complete successfully"
        assert node_a_activity.output_data is not None, "node_a should have output data"

        # Expected Result 4: Node A output contains expected fields
        # The output_data contains stdout_json with the parsed JSON from the script's stdout
        node_a_output = (
            node_a_activity.output_data
            if isinstance(node_a_activity.output_data, dict)
            else getattr(node_a_activity.output_data, "additional_properties", {})
        )

        assert "stdout_json" in node_a_output, f"node_a output should contain 'stdout_json' field: {node_a_output}"
        stdout_json = node_a_output["stdout_json"]
        assert "message" in stdout_json, f"node_a stdout_json should contain 'message' field: {stdout_json}"
        assert stdout_json["message"] == "Hello from Node A", (
            f"node_a message should be 'Hello from Node A', got: {stdout_json['message']}"
        )

        # Expected Result 5: Node B executed successfully
        # If expression resolution worked, node_b would have received the resolved value
        assert node_b_activity.status == ActivityStatus.COMPLETED, (
            f"node_b should complete successfully after expression resolution, got: {node_b_activity.status}"
        )

        # Expected Result 6: Node B's output should show it received the resolved value
        # The script prints "Received: <message>", which should contain the resolved value
        assert node_b_activity.output_data is not None, "node_b should have output data"
        node_b_output = (
            node_b_activity.output_data
            if isinstance(node_b_activity.output_data, dict)
            else getattr(node_b_activity.output_data, "additional_properties", {})
        )
        node_b_stdout = node_b_output.get("stdout", "")
        assert "Hello from Node A" in node_b_stdout, (
            f"node_b should have received resolved value from node_a in stdout. "
            f"Expected 'Received: Hello from Node A', got stdout: {node_b_stdout}"
        )

    def test_multiple_expression_references(
        self,
        syntara_api: SyntaraApiRegistry,
        create_workflow: WorkflowFactory,
        first_project_id: UUID,
    ):
        """Test multiple ${...} expressions in a single node configuration.

        Objective: Verify that multiple expression references in config.environment are all resolved.

        Test Procedure:
        1. Create a workflow where Node B references multiple fields from Node A via config.environment
        2. Execute the workflow
        3. Verify all expressions were resolved

        Expected Results:
        - All ${node_a.stdout_json.*} expressions in config.environment are resolved
        - Node B receives all referenced values as environment variables
        """
        workflow_name = unique_name("e2e-multi-expression")

        workflow_id, _ = create_workflow(
            api=syntara_api,
            project_id=first_project_id,
            name=workflow_name,
            definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "node_a",
                    "name": "Data Producer",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": ('print(\'{"name": "test-user", "team": "engineering", "role": "admin"}\')'),
                    },
                },
                {
                    "id": "node_b",
                    "name": "Data Consumer",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": (
                            "import os; "
                            "name = os.environ.get('USER_NAME', 'unknown'); "
                            "team = os.environ.get('USER_TEAM', 'none'); "
                            "role = os.environ.get('USER_ROLE', 'guest'); "
                            "print(f'User: {name}, Team: {team}, Role: {role}')"
                        ),
                        "environment": {
                            "USER_NAME": "${node_a.stdout_json.name}",
                            "USER_TEAM": "${node_a.stdout_json.team}",
                            "USER_ROLE": "${node_a.stdout_json.role}",
                        },
                    },
                },
                edges=[
                    {"from": "trigger_manual", "to": "node_a"},
                    {"from": "node_a", "to": "node_b"},
                ],
            ),
        )

        # Execute workflow
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow_id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final_execution = poll_execution_until_complete(syntara_api, execution.id)

        # Verify execution completed
        assert final_execution.status == ExecutionStatus.COMPLETED, (
            f"Execution should complete successfully, got: {final_execution.status}"
        )

        # Verify both nodes completed
        activities_by_id = {activity.activity_id: activity for activity in final_execution.activities}

        assert "node_a" in activities_by_id, "node_a should exist"
        assert "node_b" in activities_by_id, "node_b should exist"

        node_a = activities_by_id["node_a"]
        node_b = activities_by_id["node_b"]

        assert node_a.status == "completed", "node_a should complete"
        assert node_b.status == "completed", "node_b should complete after all expressions resolved"

        # Verify node_a produced the expected output structure
        assert node_a.output_data is not None, "node_a should have output data"
        node_a_output = (
            node_a.output_data
            if isinstance(node_a.output_data, dict)
            else getattr(node_a.output_data, "additional_properties", {})
        )

        assert "stdout_json" in node_a_output, "node_a output should have 'stdout_json' field"
        stdout_json = node_a_output["stdout_json"]

        assert "name" in stdout_json, "node_a stdout_json should have 'name' field"
        assert "team" in stdout_json, "node_a stdout_json should have 'team' field"
        assert "role" in stdout_json, "node_a stdout_json should have 'role' field"

        assert stdout_json["name"] == "test-user"
        assert stdout_json["team"] == "engineering"
        assert stdout_json["role"] == "admin"

        # Verify node_b received all resolved values
        assert node_b.output_data is not None, "node_b should have output data"
        node_b_output = (
            node_b.output_data
            if isinstance(node_b.output_data, dict)
            else getattr(node_b.output_data, "additional_properties", {})
        )
        node_b_stdout = node_b_output.get("stdout", "")

        # Script prints "User: {name}, Team: {team}, Role: {role}"
        assert "test-user" in node_b_stdout, (
            f"node_b should have received resolved user_name. Expected 'test-user' in stdout, got: {node_b_stdout}"
        )
        assert "engineering" in node_b_stdout, (
            f"node_b should have received resolved user_team. Expected 'engineering' in stdout, got: {node_b_stdout}"
        )
        assert "admin" in node_b_stdout, (
            f"node_b should have received resolved user_role. Expected 'admin' in stdout, got: {node_b_stdout}"
        )

    def test_trigger_input_reference_resolution(
        self,
        syntara_api: SyntaraApiRegistry,
        create_workflow: WorkflowFactory,
        first_project_id: UUID,
    ):
        """Test that ${trigger_node.field} expressions resolve trigger output values.

        Test Plan: API-19 (PARTIALLY COVERED — trigger input path)

        NOTE: API-19 specifies ${inputs.*}. There is no inputs namespace; use
        ${trigger.*} or ${trigger_id.field}. This test covers the
        ${trigger_manual.*} path.

        This test uses ${trigger_manual.*}, which references the trigger node's output.
        Trigger nodes receive input_data from ExecutionCreate and output it, making their outputs
        available to downstream nodes via ${trigger_id.field} expressions.

        Objective: Verify that downstream nodes can reference trigger node outputs via config.environment.

        Test Procedure:
        1. Create a workflow with a manual trigger
        2. Create a node that references ${trigger_manual.field} in config.environment
        3. Execute the workflow with input_data
        4. Verify the node received the trigger output values as environment variables

        Expected Results:
        - ${trigger_manual.field} in config.environment resolves to the trigger output value
        - Values are substituted before node execution and passed as env vars
        """
        workflow_name = unique_name("e2e-trigger-inputs")

        # Create workflow where a script node references trigger inputs
        workflow_id, _ = create_workflow(
            api=syntara_api,
            project_id=first_project_id,
            name=workflow_name,
            definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "process_input",
                    "name": "Process Trigger Input",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": (
                            "import os; "
                            "user = os.environ.get('USERNAME', 'unknown'); "
                            "action = os.environ.get('ACTION', 'none'); "
                            "print(f'Processing: user={user}, action={action}')"
                        ),
                        "environment": {
                            "USERNAME": "${trigger_manual.username}",
                            "ACTION": "${trigger_manual.action}",
                        },
                    },
                },
                edges=[{"from": "trigger_manual", "to": "process_input"}],
            ),
        )

        # Execute workflow with trigger inputs
        execution = syntara_api.executions.create(
            body=ExecutionCreate(
                workflow_id=workflow_id,
                trigger_node_id="trigger_manual",
                input_data=ExecutionCreateInputData.from_dict({"username": "test-user", "action": "deploy"}),
            )
        ).assert_and_get()

        # Wait for completion
        final_execution = poll_execution_until_complete(syntara_api, execution.id)

        # Verify execution completed
        assert final_execution.status == ExecutionStatus.COMPLETED, (
            f"Execution should complete successfully, got: {final_execution.status}"
        )

        # Verify node received resolved input values
        activities_by_id = {activity.activity_id: activity for activity in final_execution.activities}

        assert "process_input" in activities_by_id, "process_input activity should exist"
        process_activity = activities_by_id["process_input"]

        assert process_activity.status == "completed", "process_input should complete after trigger input resolution"

        # Verify the script executed with resolved values from trigger inputs
        assert process_activity.output_data is not None, "Activity should have output"
        process_output = (
            process_activity.output_data
            if isinstance(process_activity.output_data, dict)
            else getattr(process_activity.output_data, "additional_properties", {})
        )
        process_stdout = process_output.get("stdout", "")

        # Script prints "Processing: user={user}, action={action}"
        assert "test-user" in process_stdout, (
            f"process_input should have received resolved username from trigger inputs. "
            f"Expected 'test-user' in stdout, got: {process_stdout}"
        )
        assert "deploy" in process_stdout, (
            f"process_input should have received resolved action from trigger inputs. "
            f"Expected 'deploy' in stdout, got: {process_stdout}"
        )

    def test_workflow_context_execution_id_resolves(
        self,
        syntara_api: SyntaraApiRegistry,
        create_workflow: WorkflowFactory,
        first_project_id: UUID,
    ):
        """${workflow_context.execution.id} resolves to the current execution's UUID.

        Objective: Verify that the workflow_context.execution namespace is injected
        before nodes run and that ${workflow_context.execution.id} resolves to the
        actual execution ID recorded in the database.

        The engine pre-generates the execution ID before starting the Temporal workflow
        and injects it via the workflow_context namespace. This is the correct path for
        API-19's ${execution.id} intent — the literal ${execution.id} syntax is not
        implemented; ${workflow_context.execution.id} is.

        Test Procedure:
        1. Create a workflow with one script node that prints $EXEC_ID, where EXEC_ID
           is set via ${workflow_context.execution.id} in config.environment.
        2. Execute the workflow and capture the execution ID from the API response.
        3. Poll to terminal.

        Expected Results:
        - Execution completes successfully.
        - The node's stdout contains the execution UUID that was returned by the API,
          confirming ${workflow_context.execution.id} resolved to the correct value.
        """
        workflow_name = unique_name("e2e-wf-ctx-exec-id")

        workflow_id, _ = create_workflow(
            api=syntara_api,
            project_id=first_project_id,
            name=workflow_name,
            definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "print_exec_id",
                    "name": "Print Execution ID",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "exec_id=$EXEC_ID"',
                        "environment": {
                            "EXEC_ID": "${workflow_context.execution.id}",
                        },
                    },
                },
                edges=[{"from": "trigger_manual", "to": "print_exec_id"}],
            ),
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow_id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        execution_id = str(execution.id)
        final = poll_execution_until_complete(syntara_api, execution.id)

        assert final.status == ExecutionStatus.COMPLETED, (
            f"Expected completed, got {final.status}: {final.error_details}"
        )

        activities = {a.activity_id: a for a in (final.activities or [])}
        assert "print_exec_id" in activities, f"print_exec_id activity missing: {list(activities)}"

        activity = activities["print_exec_id"]
        assert activity.status == "completed", f"print_exec_id should complete, got: {activity.status}"

        assert activity.output_data is not None, "print_exec_id should have output data"
        output = (
            activity.output_data
            if isinstance(activity.output_data, dict)
            else getattr(activity.output_data, "additional_properties", {})
        )
        stdout = output.get("stdout", "")
        assert execution_id in stdout, (
            f"${{workflow_context.execution.id}} should resolve to {execution_id!r}. Got stdout: {stdout!r}"
        )


class TestUnresolvableExpressionError:
    """API-20: Unresolvable ${...} expressions fail the consuming node with a clear error.

    Expression resolution runs synchronously before an activity executes. When a
    referenced path (node, field, or nested key) does not exist at runtime, the engine
    raises a KeyError with a message that names the missing path component. The node is
    recorded as failed and — depending on continue_on_failure — either terminates the
    workflow or allows it to proceed.
    """

    def test_unresolvable_field_reference_fails_execution(
        self,
        syntara_api: SyntaraApiRegistry,
        create_workflow: WorkflowFactory,
        first_project_id: UUID,
    ):
        """Referencing a nonexistent field on an upstream node terminates the workflow as FAILED.

        Objective: Verify that a ${node_a.nonexistent_field} expression that cannot be
        resolved at runtime causes the consuming node to fail and the execution to reach
        FAILED status. The error recorded on the activity must identify the missing path.

        Test Procedure:
        1. Create a two-node workflow:
           - node_a: bash script that outputs plain text (no stdout_json, so
             nonexistent_field is guaranteed absent from its namespace entry).
           - node_b: references ${node_a.nonexistent_field} in config.environment.
             No continue_on_failure configured.
        2. Execute the workflow.
        3. Poll to terminal.

        Expected Results:
        - Execution status is FAILED (unhandled node failure propagates upward).
        - node_b appears in activities with a non-completed status.
        - node_b.error_details contains the unresolvable path identifier so the caller
          can diagnose which expression failed.
        """
        workflow_name = unique_name("e2e-unresolvable-expr-fail")

        workflow_id, _ = create_workflow(
            api=syntara_api,
            project_id=first_project_id,
            name=workflow_name,
            definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "node_a",
                    "name": "Producer",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "plain text — no structured output"',
                    },
                },
                {
                    "id": "node_b",
                    "name": "Consumer with bad ref",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "value=$VALUE"',
                        "environment": {
                            "VALUE": "${node_a.nonexistent_field}",
                        },
                    },
                },
                edges=[
                    {"from": "trigger_manual", "to": "node_a"},
                    {"from": "node_a", "to": "node_b"},
                ],
            ),
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow_id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)

        assert final.status == ExecutionStatus.FAILED, (
            f"Expected FAILED when expression is unresolvable, got {final.status}: {final.error_details}"
        )

        activities = {a.activity_id: a for a in (final.activities or [])}
        assert "node_b" in activities, (
            f"node_b must appear in activities so the caller can inspect the failure: {list(activities)}"
        )

        node_b = activities["node_b"]
        assert node_b.status != "completed", (
            f"node_b must not complete when its expression is unresolvable, got: {node_b.status}"
        )

        # Error details must name the specific missing field so the caller can diagnose it.
        assert node_b.error_details is not None, "node_b error_details must be set on a failed node"
        assert "nonexistent_field" in node_b.error_details, (
            f"error_details should identify the missing field name. Got: {node_b.error_details!r}"
        )

    def test_unresolvable_expression_with_continue_on_failure(
        self,
        syntara_api: SyntaraApiRegistry,
        create_workflow: WorkflowFactory,
        first_project_id: UUID,
    ):
        """Unresolvable expression with continue_on_failure fails the node but lets downstream proceed.

        Objective: When a node that references an unresolvable expression has
        continue_on_failure=true, the resolution failure is absorbed: the node is
        marked failed, the engine continues routing through it, downstream nodes execute,
        and the execution reaches COMPLETED_WITH_ERRORS rather than FAILED.

        Test Procedure:
        1. Create a three-node workflow:
           - node_a: produces output.
           - node_bad: references ${node_a.nonexistent_field}, has continue_on_failure=true.
           - node_ok: script with no expressions; connected directly after node_bad.
        2. Execute the workflow.
        3. Poll to terminal.

        Expected Results:
        - Execution status is COMPLETED_WITH_ERRORS.
        - node_bad is in activities with a non-completed status.
        - node_bad.error_details names the missing field.
        - node_ok completes — COF causes the engine to continue routing through node_bad
          to its downstream nodes despite the failure.
        """
        workflow_name = unique_name("e2e-unresolvable-expr-cof")

        workflow_id, _ = create_workflow(
            api=syntara_api,
            project_id=first_project_id,
            name=workflow_name,
            definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "node_a",
                    "name": "Producer",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "plain text"',
                    },
                },
                {
                    "id": "node_bad",
                    "name": "Bad Expression",
                    "type": "script",
                    "settings": {"continue_on_failure": True},
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "value=$VALUE"',
                        "environment": {
                            "VALUE": "${node_a.nonexistent_field}",
                        },
                    },
                },
                {
                    "id": "node_ok",
                    "name": "Independent Node",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "independent step"',
                    },
                },
                edges=[
                    {"from": "trigger_manual", "to": "node_a"},
                    {"from": "node_a", "to": "node_bad"},
                    {"from": "node_bad", "to": "node_ok"},
                ],
            ),
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow_id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)

        assert final.status == ExecutionStatus.COMPLETED_WITH_ERRORS, (
            f"Expected COMPLETED_WITH_ERRORS when COF absorbs resolution failure, "
            f"got {final.status}: {final.error_details}"
        )

        activities = {a.activity_id: a for a in (final.activities or [])}
        assert "node_bad" in activities, f"node_bad must appear in activities: {list(activities)}"

        node_bad = activities["node_bad"]
        assert node_bad.status != "completed", (
            f"node_bad must not complete when expression is unresolvable, got: {node_bad.status}"
        )

        assert node_bad.error_details is not None, "node_bad error_details must be set on a failed node"
        assert "nonexistent_field" in node_bad.error_details, (
            f"error_details should identify the missing field name. Got: {node_bad.error_details!r}"
        )

        # COF routes through the failed node — node_ok must complete.
        assert "node_ok" in activities, (
            f"node_ok must execute — COF continues routing through the failed node: {list(activities)}"
        )
        assert activities["node_ok"].status == "completed", (
            f"node_ok should complete after COF absorbs node_bad's failure, got: {activities['node_ok'].status}"
        )

    def test_completely_nonexistent_node_namespace_fails_execution(
        self,
        syntara_api: SyntaraApiRegistry,
        create_workflow: WorkflowFactory,
        first_project_id: UUID,
    ):
        """Referencing a node that does not exist in the graph at all fails at runtime.

        Objective: Verify the "namespace not found" error path — distinct from
        "key not found in namespace". When ${ghost_node.output} is used and ghost_node
        is not in the workflow graph, the resolver raises KeyError at runtime with a
        message naming the missing namespace. The execution must reach FAILED status.

        Validation issues are now recorded but do not block save, so the workflow
        is saved successfully despite referencing a nonexistent node. This lets us
        test runtime error handling when validation is not the gatekeeper.

        Test Procedure:
        1. Create a workflow (save succeeds despite validation issues):
           - node_a: runs successfully.
           - node_b: references ${ghost_node.output} where ghost_node is absent from
             the workflow's node list entirely.
        2. Execute the workflow.
        3. Poll to terminal.

        Expected Results:
        - Execution status is FAILED.
        - node_b is in activities with a non-completed status.
        - node_b.error_details names "ghost_node" as the unresolvable namespace.
        """
        workflow_name = unique_name("e2e-unresolvable-namespace")

        workflow_def = _workflow_definition_with_nodes(
            workflow_name,
            {
                "id": "node_a",
                "name": "Producer",
                "type": "script",
                "parameters": {
                    "language": "bash",
                    "code": 'echo "hello"',
                },
            },
            {
                "id": "node_b",
                "name": "Consumer with ghost namespace",
                "type": "script",
                "parameters": {
                    "language": "bash",
                    "code": 'echo "value=$VALUE"',
                    "environment": {
                        "VALUE": "${ghost_node.output}",
                    },
                },
            },
            edges=[
                {"from": "trigger_manual", "to": "node_a"},
                {"from": "node_a", "to": "node_b"},
            ],
        )

        workflow_id, _ = create_workflow(
            api=syntara_api,
            project_id=first_project_id,
            name=workflow_name,
            definition=workflow_def,
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow_id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)

        assert final.status == ExecutionStatus.FAILED, (
            f"Expected FAILED when namespace is nonexistent, got {final.status}: {final.error_details}"
        )

        activities = {a.activity_id: a for a in (final.activities or [])}
        assert "node_b" in activities, (
            f"node_b must appear in activities so the failure is inspectable: {list(activities)}"
        )

        node_b = activities["node_b"]
        assert node_b.status != "completed", (
            f"node_b must not complete when its namespace is unresolvable, got: {node_b.status}"
        )

        assert node_b.error_details is not None, "node_b error_details must be set on a failed node"
        assert "ghost_node" in node_b.error_details, (
            f"error_details should name the missing namespace 'ghost_node'. Got: {node_b.error_details!r}"
        )
