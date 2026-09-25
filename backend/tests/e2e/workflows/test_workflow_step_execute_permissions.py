"""E2E scenarios for workflow step execute permissions.

Requirements-discovery suite: documents expected behavior and interactions.
Feature is not implemented yet — entire module is skipped until it lands.

Scenario map: backend/docs/step-execute-test-scenarios.md

Prose and comments say "step". Authz resource type id remains ``workflow_node``.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import _retry_api_call, poll_execution_until_complete
from syntara_api_client.models.execution_create import ExecutionCreate
from syntara_api_client.models.policy_create import PolicyCreate
from syntara_api_client.models.policy_statement_schema import PolicyStatementSchema
from syntara_api_client.models.policy_statement_schema_conditions_type_0 import (
    PolicyStatementSchemaConditionsType0,
)
from syntara_api_client.models.test_execution_create import TestExecutionCreate
from syntara_api_client.models.test_execution_create_pre_resolved_nodes import (
    TestExecutionCreatePreResolvedNodes,
)
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_definition import WorkflowDefinition

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.workflow_read import WorkflowRead

    WorkflowFactory = Callable[[WorkflowCreate], WorkflowRead]

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skip(reason="step execute permissions not implemented"),
]


def _conditions_labels(labels: dict[str, str]) -> PolicyStatementSchemaConditionsType0:
    """Build statement conditions matching resource_labels (step attributes)."""
    return PolicyStatementSchemaConditionsType0.from_dict({"resource_labels": labels})


def _deny_step_execute_policy(
    *,
    name: str,
    labels: dict[str, str],
    scope: str = "project",
) -> PolicyCreate:
    """Deny ``workflow_node:execute`` when step labels match."""
    return PolicyCreate(
        name=name,
        statements=[
            PolicyStatementSchema(
                effect="deny",
                actions=["workflow_node:execute"],
                scope=scope,
                conditions=_conditions_labels(labels),
            )
        ],
    )


def _linear_script_definition(
    name: str,
    *,
    language: str = "bash",
    continue_on_failure: bool | None = None,
) -> dict:
    """Start → one script step."""
    settings: dict = {}
    if continue_on_failure is not None:
        settings["continue_on_failure"] = continue_on_failure
    step: dict = {
        "id": "step_script",
        "name": "Script step",
        "type": "script",
        "parameters": {"language": language, "code": 'echo "ok"'},
    }
    if settings:
        step["settings"] = settings
    return {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [step],
        "edges": [{"from": "trigger_manual", "to": "step_script"}],
    }


def _parallel_definition(name: str) -> dict:
    """Start fans out to denied (python) and allowed (bash) script steps."""
    return {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "step_python",
                "name": "Python step",
                "type": "script",
                "parameters": {"language": "python", "code": "print('x')"},
            },
            {
                "id": "step_bash",
                "name": "Bash step",
                "type": "script",
                "parameters": {"language": "bash", "code": 'echo "ok"'},
            },
        ],
        "edges": [
            {"from": "trigger_manual", "to": "step_python"},
            {"from": "trigger_manual", "to": "step_bash"},
        ],
    }


def _chain_with_downstream(name: str, *, continue_on_failure: bool) -> dict:
    """Start → possibly-denied python → downstream bash."""
    return {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "step_python",
                "name": "Python step",
                "type": "script",
                "parameters": {"language": "python", "code": "print('x')"},
                "settings": {"continue_on_failure": continue_on_failure},
            },
            {
                "id": "step_downstream",
                "name": "Downstream step",
                "type": "script",
                "parameters": {"language": "bash", "code": 'echo "downstream"'},
            },
        ],
        "edges": [
            {"from": "trigger_manual", "to": "step_python"},
            {"from": "step_python", "to": "step_downstream"},
        ],
    }


def _activities_by_id(execution: object) -> dict[str, object]:
    activities = getattr(execution, "activities", None) or []
    return {a.activity_id: a for a in activities}


class TestStepExecuteDefaultAndLabels:
    """Default allow and label / project matching (E1, P1d)."""

    def test_default_allow_runs_script_step(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Authenticated principal can execute a script step when no deny matches."""
        wf_name = unique_name("e2e-step-exec-allow")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(_linear_script_definition(wf_name)),
            )
        )
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        by_id = _activities_by_id(final)
        assert by_id["step_script"].status == "completed"

    def test_label_deny_marks_matching_step_denied(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Deny python script → that step is DENIED and the real activity never ran."""
        # Setup: assign deny policy for kind=script, language=python to the runner.
        _ = _deny_step_execute_policy(
            name=unique_name("deny-python"),
            labels={"kind": "script", "language": "python"},
        )
        wf_name = unique_name("e2e-step-exec-deny-label")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(_linear_script_definition(wf_name, language="python")),
            )
        )
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        by_id = _activities_by_id(final)
        assert by_id["step_script"].status == "denied"
        # Policy name / reason should be visible on the activity or execution summary.

    def test_label_deny_does_not_block_other_kinds(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Same python deny must not block a bash script step."""
        wf_name = unique_name("e2e-step-exec-other-kind")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(_linear_script_definition(wf_name, language="bash")),
            )
        )
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        assert _activities_by_id(final)["step_script"].status == "completed"

    def test_project_scoped_deny(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Project-scoped deny applies only in the assigned project."""
        # Create workflows in project A (denied) and B (allowed); assert DENIED vs completed.
        assert first_project_id is not None
        pytest.fail("Wire two projects + project-scoped deny when feature lands")

    def test_full_run_still_launches_when_step_denied(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Full workflow launch succeeds; denial is reported on the step, not as a launch 403."""
        wf_name = unique_name("e2e-step-exec-launch-ok")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(_linear_script_definition(wf_name, language="python")),
            )
        )
        response = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        )
        assert response.status_code in {HTTPStatus.CREATED, HTTPStatus.OK}
        execution = response.assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        assert _activities_by_id(final)["step_script"].status == "denied"


class TestStepExecutePrincipals:
    """Invoker vs publisher (E2, P0b, P0c)."""

    def test_manual_run_uses_invoker_policies(self, syntara_api: SyntaraApiRegistry) -> None:
        """Manual run evaluates the invoker's policies, not the workflow author's."""
        pytest.fail("Create junior user with deny; run as junior; expect DENIED")

    def test_scheduled_run_uses_publisher_policies(self, syntara_api: SyntaraApiRegistry) -> None:
        """Scheduled fire evaluates the publisher's policies."""
        pytest.fail("Publish as denied principal; schedule fire; expect DENIED on matching step")

    def test_webhook_run_uses_publisher_policies(self, syntara_api: SyntaraApiRegistry) -> None:
        """Webhook trigger evaluates the publisher's policies."""
        pytest.fail("Wire webhook + publisher deny when feature lands")

    def test_eda_run_uses_publisher_policies(self, syntara_api: SyntaraApiRegistry) -> None:
        """EDA trigger evaluates the publisher's policies."""
        pytest.fail("Wire EDA + publisher deny when feature lands")

    def test_retry_keeps_original_run_principal(self, syntara_api: SyntaraApiRegistry) -> None:
        """Retry/resume keeps the original run principal."""
        pytest.fail("Retry after policy change still uses original principal (or document chosen rule)")


class TestStepExecuteBranching:
    """Parallel, sole path, join, loop, CoF (E4, P1a-b, P1f)."""

    def test_parallel_branch_unaffected_by_sibling_deny(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Denied branch stops; parallel allowed branch still completes; exec COMPLETED."""
        wf_name = unique_name("e2e-step-exec-parallel")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(_parallel_definition(wf_name)),
            )
        )
        # With python deny in place for the runner:
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        by_id = _activities_by_id(final)
        assert by_id["step_python"].status == "denied"
        assert by_id["step_bash"].status == "completed"
        assert final.status == "completed"

    def test_sole_path_denied_completed_with_errors(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Only path denied → COMPLETED_WITH_ERRORS (nothing useful ran)."""
        wf_name = unique_name("e2e-step-exec-sole-deny")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(_linear_script_definition(wf_name, language="python")),
            )
        )
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        assert final.status == "completed_with_errors"
        assert _activities_by_id(final)["step_script"].status == "denied"

    def test_join_after_denied_branch(self, syntara_api: SyntaraApiRegistry) -> None:
        """Join/converge after one inbound branch was DENIED."""
        pytest.fail("Add diamond/join definition + assertions when feature lands")

    def test_loop_body_step_denied(self, syntara_api: SyntaraApiRegistry) -> None:
        """Denied step inside a loop body does not run the real activity."""
        pytest.fail("Add loop definition + deny on body step when feature lands")

    def test_all_steps_allowed(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Multi-step graph with no deny completes."""
        wf_name = unique_name("e2e-step-exec-all-ok")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(_parallel_definition(wf_name)),
            )
        )
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        assert final.status == "completed"

    def test_continue_on_failure_false_hard_stops_branch(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Without CoF, downstream must not run after DENIED."""
        wf_name = unique_name("e2e-step-exec-cof-off")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(
                    _chain_with_downstream(wf_name, continue_on_failure=False)
                ),
            )
        )
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        by_id = _activities_by_id(final)
        assert by_id["step_python"].status == "denied"
        assert "step_downstream" not in by_id or by_id["step_downstream"].status in {"skipped", "pending"}

    def test_continue_on_failure_true_allows_downstream(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """With CoF true, downstream may run after DENIED."""
        wf_name = unique_name("e2e-step-exec-cof-on")
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(
                    _chain_with_downstream(wf_name, continue_on_failure=True)
                ),
            )
        )
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        by_id = _activities_by_id(final)
        assert by_id["step_python"].status == "denied"
        assert by_id["step_downstream"].status == "completed"


class TestStepExecuteRunStep:
    """Run step API (P0e) — refuse when target execute is denied."""

    def test_run_step_allowed_target_succeeds(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Run step with an allowed target still works."""
        wf_name = unique_name("e2e-step-exec-runstep-ok")
        definition = {
            "name": wf_name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "step_a",
                    "name": "Step A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "a"'},
                },
                {
                    "id": "step_b",
                    "name": "Step B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "b"'},
                },
            ],
            "edges": [
                {"from": "trigger_manual", "to": "step_a"},
                {"from": "step_a", "to": "step_b"},
            ],
        }
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(definition),
            )
        )
        pre_resolved = TestExecutionCreatePreResolvedNodes.from_dict({"step_a": {"output": {"stdout": "mocked"}}})
        response = _retry_api_call(
            lambda: syntara_api.workflows.test_node(
                workflow_id=workflow.id,
                body=TestExecutionCreate(
                    target_node_id="step_b",
                    pre_resolved_nodes=pre_resolved,
                    trigger_node_id="trigger_manual",
                ),
            )
        )
        execution = response.assert_and_get()
        final = poll_execution_until_complete(syntara_api, execution.id)
        assert _activities_by_id(final)["step_b"].status == "completed"

    def test_run_step_denied_target_refuses_without_mocks(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Denied target → permission error; no execution; mocked predecessors must not run."""
        wf_name = unique_name("e2e-step-exec-runstep-deny")
        definition = {
            "name": wf_name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "step_a",
                    "name": "Step A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "a"'},
                },
                {
                    "id": "step_b",
                    "name": "Step B",
                    "type": "script",
                    "parameters": {"language": "python", "code": "print('b')"},
                },
            ],
            "edges": [
                {"from": "trigger_manual", "to": "step_a"},
                {"from": "step_a", "to": "step_b"},
            ],
        }
        workflow = workflow_factory(
            WorkflowCreate(
                name=wf_name,
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(definition),
            )
        )
        pre_resolved = TestExecutionCreatePreResolvedNodes.from_dict(
            {"step_a": {"output": {"stdout": "must-not-apply"}}}
        )
        response = syntara_api.workflows.test_node(
            workflow_id=workflow.id,
            body=TestExecutionCreate(
                target_node_id="step_b",
                pre_resolved_nodes=pre_resolved,
                trigger_node_id="trigger_manual",
            ),
        )
        assert response.status_code in {HTTPStatus.FORBIDDEN, HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED}
        # No execution record created for this refuse path.


class TestStepExecuteSurface:
    """API visibility and registry (P0d, P1e)."""

    def test_denied_status_visible_on_activity_api(self, syntara_api: SyntaraApiRegistry) -> None:
        """Activity list/detail exposes DENIED and denying policy / reason."""
        pytest.fail("Assert activity status and denial metadata on GET execution when feature lands")

    def test_resource_actions_lists_step_execute(self, syntara_api: SyntaraApiRegistry) -> None:
        """Resource actions / registry lists workflow_node execute for policy authoring."""
        # Prefer /resource_actions or equivalent; assert execute action present for step resource type.
        pytest.fail("Assert resource_actions includes workflow_node:execute when seeded")
