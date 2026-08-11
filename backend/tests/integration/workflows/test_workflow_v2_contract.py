"""Contract tests for V2 workflow definitions.

These tests validate the V2 workflow API contract:
- Workflow definition structure (schema_version, triggers, nodes, edges)
- Node type configuration schemas
- Edge and trigger structure
- Workflow execution result response schema

These are unit-level contract tests -- no database or Temporal required.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from syntara.core.exceptions import SafeValueError
from syntara.workflows.validators.workflow_definition import WorkflowValidator
from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.models.responses import WorkflowResultResponse
from syntara.workflows.workflow_engine.models.workflow_definition import (
    AAPJobTemplateExecutorParameters,
    AgenticExecutorParameters,
    APIExecutorParameters,
    HTTPMethod,
    ScriptExecutorParameters,
    ScriptLanguage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_workflow(**overrides: object) -> dict[str, Any]:
    """Build a minimal valid V2 workflow definition."""
    base: dict[str, Any] = {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "description": "A test workflow",
        "triggers": [
            {"id": "trigger_1", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "script_1",
                "type": "script",
                "parameters": {"language": "python", "code": "print('hello')"},
            },
        ],
        "edges": [
            {"from": "trigger_1", "to": "script_1"},
        ],
    }
    base.update(overrides)
    return base


def _multi_node_workflow() -> dict[str, Any]:
    """Build a workflow with trigger -> condition -> script / converge."""
    return {
        "schema_version": "2.0.0",
        "name": "multi-node-workflow",
        "triggers": [
            {"id": "trigger_1", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "cond_1",
                "type": "condition",
                "parameters": {"condition": "${input.value} > 10"},
            },
            {
                "id": "script_true",
                "type": "script",
                "parameters": {"language": "python", "code": "print('true branch')"},
            },
            {
                "id": "script_false",
                "type": "script",
                "parameters": {"language": "python", "code": "print('false branch')"},
            },
            {
                "id": "converge_1",
                "type": "converge",
                "parameters": {},
            },
        ],
        "edges": [
            {"from": "trigger_1", "to": "cond_1"},
            {"from": "cond_1", "to": "script_true", "from_port": "true"},
            {"from": "cond_1", "to": "script_false", "from_port": "false"},
            {"from": "script_true", "to": "converge_1"},
            {"from": "script_false", "to": "converge_1"},
        ],
    }


# ---------------------------------------------------------------------------
# WorkflowValidator contract
# ---------------------------------------------------------------------------


class TestWorkflowDefinitionStructure:
    """Validate that WorkflowValidator enforces the V2 definition contract."""

    def setup_method(self) -> None:
        self.validator = WorkflowValidator()

    def test_valid_minimal_workflow(self) -> None:
        """A minimal valid V2 workflow passes validation."""
        self.validator.validate_workflow_definition(_minimal_workflow())

    def test_requires_schema_version_2(self) -> None:
        """Workflow must declare schema_version '2.0.0'."""
        defn = _minimal_workflow(schema_version="1.0.0")
        with pytest.raises(SafeValueError, match="schema_version"):
            self.validator.validate_workflow_definition(defn)

    def test_rejects_missing_schema_version(self) -> None:
        """Missing schema_version is rejected."""
        defn = _minimal_workflow()
        del defn["schema_version"]
        with pytest.raises(SafeValueError, match="schema_version"):
            self.validator.validate_workflow_definition(defn)

    def test_requires_triggers_field(self) -> None:
        """Workflow must have a 'triggers' field."""
        defn = _minimal_workflow()
        del defn["triggers"]
        with pytest.raises(SafeValueError, match="triggers"):
            self.validator.validate_workflow_definition(defn)

    def test_requires_nodes_field(self) -> None:
        """Workflow must have a 'nodes' field."""
        defn = _minimal_workflow()
        del defn["nodes"]
        with pytest.raises(SafeValueError, match="nodes"):
            self.validator.validate_workflow_definition(defn)

    def test_requires_edges_field(self) -> None:
        """Workflow must have an 'edges' field."""
        defn = _minimal_workflow()
        del defn["edges"]
        with pytest.raises(SafeValueError, match="edges"):
            self.validator.validate_workflow_definition(defn)


# ---------------------------------------------------------------------------
# WorkflowGraph contract
# ---------------------------------------------------------------------------


class TestWorkflowGraphConstruction:
    """Validate WorkflowGraph.from_dict() enforces graph structure."""

    def test_builds_graph_from_valid_definition(self) -> None:
        """Graph builds successfully from a valid definition."""
        graph = WorkflowGraph.from_dict(_minimal_workflow())
        nodes = graph.get_all_nodes()
        # trigger + 1 script node
        assert len(nodes) == 2

    def test_graph_preserves_metadata(self) -> None:
        """Graph stores schema_version, name, description as metadata."""
        defn = _minimal_workflow()
        graph = WorkflowGraph.from_dict(defn)
        assert graph.metadata["schema_version"] == "2.0.0"
        assert graph.metadata["name"] == "test-workflow"

    def test_trigger_nodes_detected(self) -> None:
        """Nodes whose type ends with '_trigger' are identified as triggers."""
        graph = WorkflowGraph.from_dict(_minimal_workflow())
        triggers = graph.get_trigger_nodes()
        assert len(triggers) == 1
        assert triggers[0].type == "manual_trigger"

    def test_edge_traversal(self) -> None:
        """Successors are reachable via edges."""
        graph = WorkflowGraph.from_dict(_minimal_workflow())
        successors = graph.get_next_activities("trigger_1")
        assert len(successors) == 1
        assert successors[0].id == "script_1"

    def test_rejects_edge_to_nonexistent_node(self) -> None:
        """Graph rejects edges referencing nodes that don't exist."""
        defn = _minimal_workflow()
        defn["edges"].append({"from": "script_1", "to": "ghost_node"})
        with pytest.raises(ValueError, match="non-existent node"):
            WorkflowGraph.from_dict(defn)

    def test_rejects_workflow_without_trigger(self) -> None:
        """Graph requires at least one trigger node."""
        defn = _minimal_workflow()
        defn["triggers"] = []
        # The trigger is gone, so the edge from trigger_1 will also fail
        # Use a definition with no triggers and adjust edges
        defn = {
            "schema_version": "2.0.0",
            "nodes": [
                {"id": "script_1", "type": "script", "parameters": {"language": "python", "code": "x=1"}},
            ],
            "edges": [],
        }
        with pytest.raises(ValueError, match="trigger"):
            WorkflowGraph.from_dict(defn)

    def test_detects_orphan_node(self) -> None:
        """Graph rejects non-trigger nodes with no edges."""
        defn = _minimal_workflow()
        defn["nodes"].append(
            {"id": "orphan", "type": "script", "parameters": {"language": "python", "code": "x=1"}},
        )
        with pytest.raises(ValueError, match="Orphan node"):
            WorkflowGraph.from_dict(defn)

    def test_multi_node_with_condition_and_converge(self) -> None:
        """Graph builds with condition branches converging."""
        graph = WorkflowGraph.from_dict(_multi_node_workflow())
        # condition has two outgoing ports
        true_branch = graph.get_next_activities_by_port("cond_1", "true")
        false_branch = graph.get_next_activities_by_port("cond_1", "false")
        assert len(true_branch) == 1
        assert true_branch[0].id == "script_true"
        assert len(false_branch) == 1
        assert false_branch[0].id == "script_false"


# ---------------------------------------------------------------------------
# Edge structure contract
# ---------------------------------------------------------------------------


class TestEdgeStructure:
    """Validate edge dict structure (from, to, optional ports)."""

    def test_basic_edge(self) -> None:
        """Edge with only 'from' and 'to' is valid."""
        graph = WorkflowGraph.from_dict(_minimal_workflow())
        edges = graph.get_outgoing_edges("trigger_1")
        assert len(edges) == 1
        assert edges[0]["from"] == "trigger_1"
        assert edges[0]["to"] == "script_1"

    def test_edge_with_from_port(self) -> None:
        """Edge with from_port carries the port attribute."""
        graph = WorkflowGraph.from_dict(_multi_node_workflow())
        edges = graph.get_outgoing_edges("cond_1")
        ports = {e.get("from_port") for e in edges}
        assert "true" in ports
        assert "false" in ports

    def test_edge_with_to_port_iterate_skipped(self) -> None:
        """Edges with to_port='iterate' are filtered out (loop feedback)."""
        defn = _minimal_workflow()
        defn["nodes"].append(
            {"id": "loop_1", "type": "loop", "parameters": {"condition": "true", "type": "while"}},
        )
        defn["edges"].append({"from": "script_1", "to": "loop_1"})
        defn["edges"].append({"from": "loop_1", "to": "script_1", "to_port": "iterate"})
        defn["edges"].append({"from": "loop_1", "to": "trigger_1", "from_port": "complete"})
        # The iterate edge should be skipped during graph construction
        graph = WorkflowGraph.from_dict(defn)
        outgoing = graph.get_outgoing_edges("loop_1")
        to_ports = [e.get("to_port") for e in outgoing]
        assert "iterate" not in to_ports


# ---------------------------------------------------------------------------
# Trigger structure contract
# ---------------------------------------------------------------------------


class TestTriggerStructure:
    """Validate trigger dict structure."""

    def test_trigger_has_id_and_type(self) -> None:
        """Triggers must have 'id' and 'type' fields."""
        graph = WorkflowGraph.from_dict(_minimal_workflow())
        triggers = graph.get_trigger_nodes()
        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.id == "trigger_1"
        assert trigger.type == "manual_trigger"

    def test_multiple_triggers(self) -> None:
        """Workflow can have multiple triggers."""
        defn = _minimal_workflow()
        defn["triggers"].append(
            {"id": "trigger_2", "type": "webhook_trigger", "parameters": {}},
        )
        defn["edges"].append({"from": "trigger_2", "to": "script_1"})
        graph = WorkflowGraph.from_dict(defn)
        triggers = graph.get_trigger_nodes()
        assert len(triggers) == 2
        trigger_ids = {t.id for t in triggers}
        assert trigger_ids == {"trigger_1", "trigger_2"}


# ---------------------------------------------------------------------------
# Node type config contracts
# ---------------------------------------------------------------------------


class TestScriptNodeParameters:
    """Validate ScriptExecutorParameters contract."""

    def test_valid_python_script(self) -> None:
        """Python script with code and language is valid."""
        config = ScriptExecutorParameters(language=ScriptLanguage.PYTHON, code="print('hi')")
        assert config.language == ScriptLanguage.PYTHON
        assert config.code == "print('hi')"

    def test_valid_bash_script(self) -> None:
        """Bash script is a valid language option."""
        config = ScriptExecutorParameters(language=ScriptLanguage.BASH, code="echo hi")
        assert config.language == ScriptLanguage.BASH

    def test_rejects_empty_code(self) -> None:
        """Script node requires non-empty code."""
        with pytest.raises(ValidationError, match="code"):
            ScriptExecutorParameters(language=ScriptLanguage.PYTHON, code="")

    def test_template_expression_bypasses_validation(self) -> None:
        """Template expressions like ${input.code} bypass field validation."""
        config = ScriptExecutorParameters(language=ScriptLanguage.PYTHON, code="${input.code}")
        assert config.code == "${input.code}"


class TestAPIExecutorParameters:
    """Validate APIExecutorParameters (http_request) contract."""

    def test_valid_get_request(self) -> None:
        """GET request with url and method is valid."""
        config = APIExecutorParameters(method=HTTPMethod.GET, url="https://example.com/api")
        assert config.url == "https://example.com/api"

    def test_valid_post_with_body(self) -> None:
        """POST request can include a body."""
        config = APIExecutorParameters(
            method=HTTPMethod.POST,
            url="https://example.com/api",
            body={"key": "value"},
        )
        assert config.body == {"key": "value"}

    def test_requires_method(self) -> None:
        """HTTP method is required."""
        with pytest.raises(ValidationError, match="method"):
            APIExecutorParameters(url="https://example.com")  # type: ignore[call-arg]

    def test_url_is_optional(self) -> None:
        """URL is optional (can be provided by a Secret URL credential at runtime)."""
        config = APIExecutorParameters(method=HTTPMethod.GET)
        assert config.url is None


class TestAgenticExecutorParameters:
    """Validate AgenticExecutorParameters contract."""

    def test_valid_agentic_config(self) -> None:
        """Agentic config with prompt is valid."""
        config = AgenticExecutorParameters(prompt="Analyze this data")
        assert config.prompt == "Analyze this data"

    def test_optional_agent_and_llm_model_id(self) -> None:
        """Agent and llm_model_id fields are optional."""
        config = AgenticExecutorParameters(prompt="Do something")
        assert config.agent is None
        assert config.llm_model_id is None

    def test_rejects_null_bytes_in_prompt(self) -> None:
        """Prompt with null bytes is rejected for security."""
        with pytest.raises((ValidationError, SafeValueError)):
            AgenticExecutorParameters(prompt="bad\0prompt")

    def test_file_ids_must_be_valid_uuids(self) -> None:
        """File IDs must be valid UUID format."""
        with pytest.raises((ValidationError, SafeValueError)):
            AgenticExecutorParameters(prompt="test", file_ids=["not-a-uuid"])

    def test_file_ids_with_template_allowed(self) -> None:
        """Template expressions in file_ids bypass UUID validation."""
        config = AgenticExecutorParameters(prompt="test", file_ids=["${input.file_id}"])
        assert config.file_ids == ["${input.file_id}"]


class TestAAPJobTemplateConfig:
    """Validate AAPJobTemplateExecutorParameters contract."""

    def test_valid_by_id(self) -> None:
        """Job template config with job_template_id is valid."""
        config = AAPJobTemplateExecutorParameters(job_template_id=42)
        assert config.job_template_id == 42

    def test_valid_by_name(self) -> None:
        """Job template config with name + org is valid."""
        config = AAPJobTemplateExecutorParameters(
            job_template_name="my-template",
            organization_name="my-org",
        )
        assert config.job_template_name == "my-template"

    def test_rejects_name_without_org(self) -> None:
        """Job template name requires organization_name."""
        with pytest.raises((ValidationError, SafeValueError), match="organization_name"):
            AAPJobTemplateExecutorParameters(job_template_name="my-template")

    def test_rejects_missing_id_and_name(self) -> None:
        """Either job_template_id or job_template_name must be specified."""
        with pytest.raises((ValidationError, SafeValueError)):
            AAPJobTemplateExecutorParameters()

    def test_extra_vars_default_empty(self) -> None:
        """Extra vars default to empty dict."""
        config = AAPJobTemplateExecutorParameters(job_template_id=1)
        assert config.extra_vars == {}

    def test_verbosity_range(self) -> None:
        """Verbosity must be 0-5."""
        with pytest.raises(ValidationError, match="verbosity"):
            AAPJobTemplateExecutorParameters(job_template_id=1, verbosity=6)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WorkflowResultResponse contract
# ---------------------------------------------------------------------------


class TestWorkflowResultResponse:
    """Validate WorkflowResultResponse schema contract."""

    def test_valid_completed_result(self) -> None:
        """Completed workflow result has all expected fields."""
        result = WorkflowResultResponse(
            status="completed",
            execution_id="exec-123",
            completed_activities=["script_1", "script_2"],
            activity_outputs={
                "script_1": {"stdout": "hello", "exit_code": 0},
                "script_2": {"stdout": "world", "exit_code": 0},
            },
        )
        assert result.status == "completed"
        assert result.execution_id == "exec-123"
        assert len(result.completed_activities) == 2
        assert "script_1" in result.activity_outputs

    def test_failed_result(self) -> None:
        """Failed workflow result is valid with status 'failed'."""
        result = WorkflowResultResponse(
            status="failed",
            execution_id="exec-456",
        )
        assert result.status == "failed"
        assert result.completed_activities == []
        assert result.activity_outputs == {}

    def test_requires_status(self) -> None:
        """Status is a required field."""
        with pytest.raises(ValidationError, match="status"):
            WorkflowResultResponse(execution_id="exec-789")  # type: ignore[call-arg]

    def test_requires_execution_id(self) -> None:
        """Execution ID is a required field."""
        with pytest.raises(ValidationError, match="execution_id"):
            WorkflowResultResponse(status="completed")  # type: ignore[call-arg]

    def test_activity_outputs_defaults_to_empty(self) -> None:
        """Activity outputs defaults to empty dict when not provided."""
        result = WorkflowResultResponse(status="completed", execution_id="exec-1")
        assert result.activity_outputs == {}

    def test_completed_activities_defaults_to_empty(self) -> None:
        """Completed activities defaults to empty list when not provided."""
        result = WorkflowResultResponse(status="completed", execution_id="exec-1")
        assert result.completed_activities == []

    def test_result_serialization_round_trip(self) -> None:
        """Result can be serialized to dict and back."""
        original = WorkflowResultResponse(
            status="completed",
            execution_id="exec-rt",
            completed_activities=["a1"],
            activity_outputs={"a1": {"data": 42}},
        )
        data = original.model_dump()
        restored = WorkflowResultResponse(**data)
        assert restored.status == original.status
        assert restored.execution_id == original.execution_id
        assert restored.completed_activities == original.completed_activities
        assert restored.activity_outputs == original.activity_outputs


# ---------------------------------------------------------------------------
# Node settings validation (regression test for missing nodeSettings bug)
# ---------------------------------------------------------------------------


class TestNodeSettingsValidation:
    """Validate that workflows with node-level settings validate correctly.

    These tests ensure the schema properly validates all three tiers of node settings:
    - nodeSettingsFull: continue_on_failure + timeout + retry_policy
    - nodeSettingsNoRetry: continue_on_failure + timeout (no retry)
    - nodeSettingsCof: continue_on_failure only

    Regression coverage for the missing nodeSettings $ref bug from PR #1301.
    """

    def setup_method(self) -> None:
        self.validator = WorkflowValidator()

    def test_script_node_with_settings_no_retry_tier(self) -> None:
        """Script nodes use nodeSettingsNoRetry tier (cof + timeout, no retry)."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "script_1",
                    "type": "script",
                    "parameters": {"language": "python", "code": "print('hello')"},
                    "settings": {"continue_on_failure": True, "timeout": 300},
                },
            ],
            "edges": [{"from": "t1", "to": "script_1"}],
        }
        # Should not raise
        self.validator.validate_workflow_definition(defn)

    def test_aap_job_template_with_settings_full_tier(self) -> None:
        """AAP job template nodes use nodeSettingsFull tier (cof + timeout + retry)."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "aap_1",
                    "type": "aap_job_template",
                    "parameters": {
                        "job_template_id": 42,
                    },
                    "settings": {
                        "continue_on_failure": True,
                        "timeout": 600,
                        "retry_policy": {"max_retries": 3, "initial_interval": 10},
                    },
                },
            ],
            "edges": [{"from": "t1", "to": "aap_1"}],
        }
        # Should not raise
        self.validator.validate_workflow_definition(defn)

    def test_converge_node_with_settings_cof_tier(self) -> None:
        """Converge nodes use nodeSettingsCof tier (continue_on_failure only)."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "script_1",
                    "type": "script",
                    "parameters": {"language": "python", "code": "print('a')"},
                },
                {
                    "id": "script_2",
                    "type": "script",
                    "parameters": {"language": "python", "code": "print('b')"},
                },
                {
                    "id": "converge_1",
                    "type": "converge",
                    "parameters": {},
                    "settings": {"continue_on_failure": False},
                },
            ],
            "edges": [
                {"from": "t1", "to": "script_1"},
                {"from": "t1", "to": "script_2"},
                {"from": "script_1", "to": "converge_1"},
                {"from": "script_2", "to": "converge_1"},
            ],
        }
        # Should not raise
        self.validator.validate_workflow_definition(defn)

    def test_approval_node_with_settings_no_retry_tier(self) -> None:
        """Approval nodes use nodeSettingsNoRetry tier (cof + timeout, no retry)."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "approval_1",
                    "type": "approval",
                    "parameters": {
                        "approver_users": ["admin"],
                        "prompt": "Approve this?",
                        "fallback_decision": "reject",
                        "decision_window": 3600,
                    },
                    "settings": {"continue_on_failure": True, "timeout": 7200},
                },
            ],
            "edges": [{"from": "t1", "to": "approval_1"}],
        }
        # Should not raise
        self.validator.validate_workflow_definition(defn)

    def test_http_request_with_settings_full_tier(self) -> None:
        """HTTP request nodes use nodeSettingsFull tier (cof + timeout + retry)."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "http_1",
                    "type": "http_request",
                    "parameters": {
                        "url": "https://api.example.com/data",
                        "method": "GET",
                    },
                    "settings": {
                        "continue_on_failure": False,
                        "timeout": 30,
                        "retry_policy": {
                            "max_retries": 5,
                            "initial_interval": 2,
                            "max_interval": 60,
                            "backoff_coefficient": 2.0,
                        },
                    },
                },
            ],
            "edges": [{"from": "t1", "to": "http_1"}],
        }
        # Should not raise
        self.validator.validate_workflow_definition(defn)

    def test_rejects_retry_policy_on_script_node(self) -> None:
        """Script nodes (NoRetry tier) should reject retry_policy."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "script_1",
                    "type": "script",
                    "parameters": {"language": "python", "code": "print('hello')"},
                    "settings": {
                        "continue_on_failure": True,
                        "retry_policy": {"max_retries": 3},  # Invalid for script
                    },
                },
            ],
            "edges": [{"from": "t1", "to": "script_1"}],
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            self.validator.validate_workflow_definition(defn)

    def test_rejects_timeout_on_converge_node(self) -> None:
        """Converge nodes (Cof tier) should reject timeout."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "script_1",
                    "type": "script",
                    "parameters": {"language": "python", "code": "print('a')"},
                },
                {
                    "id": "converge_1",
                    "type": "converge",
                    "parameters": {},
                    "settings": {
                        "continue_on_failure": False,
                        "timeout": 60,  # Invalid for converge
                    },
                },
            ],
            "edges": [
                {"from": "t1", "to": "script_1"},
                {"from": "script_1", "to": "converge_1"},
            ],
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            self.validator.validate_workflow_definition(defn)

    def test_settings_field_is_optional(self) -> None:
        """Settings field is optional on all node types."""
        defn = {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "script_1",
                    "type": "script",
                    "parameters": {"language": "python", "code": "print('hello')"},
                    # No settings field - should use defaults
                },
                {
                    "id": "http_1",
                    "type": "http_request",
                    "parameters": {
                        "url": "https://api.example.com",
                        "method": "POST",
                    },
                    # No settings field - should use defaults
                },
            ],
            "edges": [
                {"from": "t1", "to": "script_1"},
                {"from": "script_1", "to": "http_1"},
            ],
        }
        # Should not raise - settings is optional
        self.validator.validate_workflow_definition(defn)
