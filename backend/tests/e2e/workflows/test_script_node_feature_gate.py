"""E2E tests for the script node feature gate (APP_SCRIPT_NODES_ENABLED).

Tests verify that:
- When disabled (default): script activities fail immediately with an opaque error
- When enabled: script activities execute normally

The feature gate is controlled by the APP_SCRIPT_NODES_ENABLED environment variable
on the Temporal worker. Since E2E tests hit a live deployment, the gate cannot be
toggled mid-test. Tests are conditionally skipped based on the environment.

NOTE: The APP_SCRIPT_NODES_ENABLED env var in the test runner's environment must
match what the Temporal worker was started with, otherwise tests may produce
misleading results.
"""

import os
from typing import Any

import pytest
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models.execution_status import ExecutionStatus

pytestmark = [pytest.mark.e2e]

_SCRIPT_NODES_ENABLED = os.environ.get("APP_SCRIPT_NODES_ENABLED", "").lower() == "true"


def _script_workflow_definition(name: str) -> dict[str, Any]:
    """Return a minimal workflow definition containing a single script node."""
    return {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "script_node",
                "name": "Feature Gate Test Script",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo 'feature gate test'"},
            },
        ],
        "edges": [{"from": "trigger", "to": "script_node"}],
    }


@pytest.mark.skipif(
    _SCRIPT_NODES_ENABLED,
    reason="APP_SCRIPT_NODES_ENABLED is true — disabled-gate tests do not apply",
)
class TestScriptNodeFeatureGateDisabled:
    """Tests for script node behavior when APP_SCRIPT_NODES_ENABLED is false (default).

    These tests verify that the Temporal worker rejects script activities
    immediately with an opaque, non-retryable error.
    """

    def test_script_activity_fails_immediately(self, nexus_api: SyntaraApiRegistry) -> None:
        """Script activity fails immediately when the feature gate is disabled."""
        result = create_and_run_workflow(
            nexus_api,
            "e2e-script-gate-disabled",
            _script_workflow_definition("script-gate-disabled"),
        )

        assert result.status == ExecutionStatus.FAILED, (
            f"Expected execution to fail when script gate is disabled, got: {result.status}"
        )

        error_text = str(result.error_details or "")
        assert "Developer Preview Script node" in error_text, (
            f"Expected 'Developer Preview Script node' in error_details, got: {error_text}"
        )

    def test_failure_visible_in_activity_history(self, nexus_api: SyntaraApiRegistry) -> None:
        """The script activity failure is recorded in per-node activity history."""
        result = create_and_run_workflow(
            nexus_api,
            "e2e-script-gate-disabled-activity",
            _script_workflow_definition("script-gate-disabled-activity"),
        )

        assert result.status == ExecutionStatus.FAILED

        assert result.activities is not None, "Execution should include activities"
        activities_by_id = {a.activity_id: a for a in result.activities}

        assert "script_node" in activities_by_id, "script_node should have an activity record"
        script_activity = activities_by_id["script_node"]
        assert script_activity.status == "failed", f"script_node should be failed, got: {script_activity.status}"

        activity_error = str(getattr(script_activity, "error_details", None) or "")
        assert "Developer Preview Script node" in activity_error, (
            f"Expected error details on script activity, got: {activity_error}"
        )

    def test_error_message_is_opaque(self, nexus_api: SyntaraApiRegistry) -> None:
        """The error message does not expose configuration details or hint at how to enable."""
        result = create_and_run_workflow(
            nexus_api,
            "e2e-script-gate-opaque",
            _script_workflow_definition("script-gate-opaque"),
        )

        assert result.status == ExecutionStatus.FAILED

        error_texts: list[str] = [str(result.error_details or "")]
        if result.activities:
            for act in result.activities:
                if act.activity_id == "script_node":
                    error_texts.append(str(getattr(act, "error_details", None) or ""))

        for error_text in error_texts:
            if not error_text:
                continue
            assert "APP_SCRIPT_NODES_ENABLED" not in error_text, f"Error must not expose env var name: {error_text}"
            assert "script_nodes_enabled" not in error_text, f"Error must not expose setting name: {error_text}"
            assert "enable" not in error_text.lower(), f"Error must not hint at how to enable: {error_text}"
            assert "setting" not in error_text.lower(), f"Error must not reference settings: {error_text}"


@pytest.mark.skipif(
    not _SCRIPT_NODES_ENABLED,
    reason="APP_SCRIPT_NODES_ENABLED is not true — enabled-gate tests require it",
)
class TestScriptNodeFeatureGateEnabled:
    """Tests for script node behavior when APP_SCRIPT_NODES_ENABLED is true.

    These tests verify that script activities execute normally when the
    feature gate is enabled.
    """

    def test_script_activity_executes_normally(self, nexus_api: SyntaraApiRegistry) -> None:
        """Script activity completes successfully when the feature gate is enabled."""
        result = create_and_run_workflow(
            nexus_api,
            "e2e-script-gate-enabled",
            _script_workflow_definition("script-gate-enabled"),
        )

        assert result.status == ExecutionStatus.COMPLETED, (
            f"Expected execution to complete, got: {result.status}. Error: {result.error_details}"
        )
        assert result.error_details is None, (
            f"Successful execution should have no error details: {result.error_details}"
        )

        assert result.activities is not None
        activities_by_id = {a.activity_id: a for a in result.activities}
        assert "script_node" in activities_by_id
        assert activities_by_id["script_node"].status == "completed", (
            f"script_node should be completed, got: {activities_by_id['script_node'].status}"
        )
