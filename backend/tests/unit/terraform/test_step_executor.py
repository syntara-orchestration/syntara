"""Contracts for native/SDK TFE execution without a live TFE or container runtime."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import yaml
from temporalio.exceptions import ApplicationError

from syntara.step_nodes.contracts import ManifestCatalog, StepContractError, StepInvocation, StepResult
from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.step_bindings import TFE_STEP_BINDINGS
from syntara.terraform.step_executor import SDKTFEStepExecutor
from syntara.terraform.step_mapping import sdk_inputs, workflow_output
from syntara.workflows.workflow_engine.activities.tfe_activities import TFE_ACTIVITIES
from syntara.workflows.workflow_engine.activities.tfe_dispatch import build_tfe_activity_registry
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

BASE: dict[str, Any] = {
    "integration_id": "11111111-1111-1111-1111-111111111111",
    "credential_id": "22222222-2222-2222-2222-222222222222",
    "_resolved_integration": {"base_url": "https://tfe.test", "organization": "acme", "verify_ssl": True},
    "_resolved_credentials": {"extra_vars": {"bearer_token": "private-token"}},
}


def descriptor(operation: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    """Minimal standalone manifest fixture for a transport contract."""
    return {
        "apiVersion": "syntara.io/v1alpha1",
        "kind": "NodeType",
        "metadata": {"name": "tfe_" + operation, "version": "0.1.0"},
        "spec": {
            "category": "action",
            "execution": {
                "type": "container",
                "image": "registry.test/tfe:0.1.0",
                "entrypoint": "python -m tfe_nodes.runner " + operation,
            },
            "inputs": {"type": "object", "properties": properties or {}},
            "outputs": {},
        },
    }


def response(
    operation: str, data: dict[str, Any] | list[dict[str, Any]] | None = None, related: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a successful runtime reply."""
    return {
        "Result": {"operation": operation, "data": data, "related": related or {}, "meta": {}, "http_status": 200},
        "StatusCode": 0,
        "StatusMessage": "ok",
        "ErrorMessage": "",
    }


class RecordingTransport:
    """Record transient requests and supply deterministic replies."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        """Keep reply and call state isolated per test."""
        self.replies = list(replies)
        self.calls: list[StepInvocation] = []

    async def execute(self, invocation: StepInvocation) -> dict[str, Any]:
        self.calls.append(invocation)
        return self.replies.pop(0)


@pytest.mark.asyncio
async def test_workspace_preset_and_output_mapping() -> None:
    transport = RecordingTransport([response("create_workspace", {"id": "ws-123", "attributes": {"name": "demo"}})])
    executor = SDKTFEStepExecutor(ManifestCatalog([descriptor("create_workspace")]), transport)
    result = await executor.execute(
        "tfe_create_workspace", {**BASE, "name": "demo", "preset": "agent", "agent_pool_id": "apool-123"}
    )
    assert result == {"workspace_id": "ws-123", "workspace_name": "demo", "organization": "acme"}
    call = transport.calls[0]
    assert call.inputs["attributes"] == {"execution-mode": "agent", "agent-pool-id": "apool-123"}
    assert call.credentials == {"token": "private-token"}
    assert "_resolved_credentials" not in call.inputs
    assert "private-token" not in repr(call)
    assert call.image == "registry.test/tfe:0.1.0"


@pytest.mark.asyncio
async def test_variable_secret_split_and_explicit_false_preserved() -> None:
    transport = RecordingTransport([response("add_variable", {"id": "var-1"})])
    catalog = ManifestCatalog([descriptor("add_variable", {"value": {"type": "string", "secret": True}})])
    executor = SDKTFEStepExecutor(catalog, transport)
    result = await executor.execute(
        "tfe_add_variable",
        {**BASE, "workspace_id": "ws-1", "key": "test", "value": "sensitive-value", "sensitive": False},
    )
    assert result == {"variable_id": "var-1"}
    assert "value" not in transport.calls[0].inputs
    assert transport.calls[0].credentials["value"] == "sensitive-value"
    assert transport.calls[0].inputs["sensitive"] is False


@pytest.mark.asyncio
async def test_run_action_precheck_prevents_mutation() -> None:
    transport = RecordingTransport([response("get_run_status", {"attributes": {"actions": {"is-confirmable": False}}})])
    executor = SDKTFEStepExecutor(ManifestCatalog([descriptor("get_run_status"), descriptor("apply_run")]), transport)
    with pytest.raises(TFEError) as error:
        await executor.execute("tfe_apply_run", {**BASE, "run_id": "run-1"})
    assert error.value.error_code == TFEErrorCode.STATE_CONFLICT
    assert len(transport.calls) == 1
    assert transport.calls[0].inputs["include_plan"] is False


@pytest.mark.asyncio
async def test_vcs_repository_is_qualified_and_native_outputs_preserved() -> None:
    transport = RecordingTransport(
        [
            response("get_installation_details", {"id": "ghain-1", "attributes": {"name": "acme"}}),
            response("link_vcs_to_workspace", {"id": "ws-1"}),
        ]
    )
    executor = SDKTFEStepExecutor(
        ManifestCatalog([descriptor("get_installation_details"), descriptor("link_vcs_to_workspace")]), transport
    )
    result = await executor.execute(
        "tfe_link_vcs",
        {**BASE, "workspace_id": "ws-1", "installation_id": "ghain-1", "repository": "app", "branch": "main"},
    )
    assert result == {"linked": True, "identifier": "acme/app", "branch": "main"}
    assert transport.calls[1].inputs["repository"] == "acme/app"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [
        {"StatusCode": 1, "Result": None, "ErrorMessage": "private-token"},
        {"StatusCode": "0", "Result": {}},
        response("wrong_operation"),
    ],
)
async def test_failed_or_invalid_sdk_envelopes_never_become_success(reply: dict[str, Any]) -> None:
    executor = SDKTFEStepExecutor(ManifestCatalog([descriptor("delete_workspace")]), RecordingTransport([reply]))
    with pytest.raises(TFEError) as error:
        await executor.execute("tfe_delete_workspace", {**BASE, "workspace_id": "ws-1"})
    assert "private-token" not in str(error.value)
    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_cancellation_propagates_without_retry() -> None:
    transport = AsyncMock()
    transport.execute.side_effect = asyncio.CancelledError
    executor = SDKTFEStepExecutor(ManifestCatalog([descriptor("delete_workspace")]), transport)
    with pytest.raises(asyncio.CancelledError):
        await executor.execute("tfe_delete_workspace", {**BASE, "workspace_id": "ws-1"})
    transport.execute.assert_awaited_once()


def test_catalog_defensive_copy_and_schema_sensitive_alias() -> None:
    manifest = descriptor("add_variable", {"value": {"type": "string", "is_secret": True}})
    catalog = ManifestCatalog([manifest])
    manifest["spec"]["execution"]["image"] = "modified"
    invocation = catalog.invocation("tfe_add_variable", {"value": "secret"}, {})
    assert invocation.image == "registry.test/tfe:0.1.0"
    assert invocation.inputs == {}
    assert invocation.credentials == {"value": "secret"}
    assert "secret" not in repr(invocation)
    with pytest.raises(StepContractError):
        catalog.invocation("tfe_add_variable", {"value": 123}, {})
    with pytest.raises(StepContractError):
        catalog.invocation("tfe_add_variable", {"value": "secret"}, {"value": "duplicate"})
    with pytest.raises(StepContractError):
        StepResult.from_payload({"StatusCode": True, "Result": {}})


def test_native_registry_is_unchanged_and_all_sdk_bindings_exist() -> None:
    registry = build_tfe_activity_registry()
    assert set(registry.values()) == set(TFE_ACTIVITIES)
    assert len(registry) == len(TFE_STEP_BINDINGS) == 28
    assert {name.value.removeprefix("execute_").removesuffix("_activity") for name in registry} == set(
        TFE_STEP_BINDINGS
    )


@pytest.mark.asyncio
async def test_worker_scoped_dispatch_preserves_names_and_errors() -> None:
    executor = AsyncMock()
    executor.execute.return_value = {"deleted": True}
    registry = build_tfe_activity_registry(executor)
    name = ActivityName.TFE_DELETE_WORKSPACE
    assert await registry[name]({**BASE, "workspace_id": "ws-1"}, None) == {"deleted": True}
    executor.execute.assert_awaited_once_with("tfe_delete_workspace", {**BASE, "workspace_id": "ws-1"}, None)
    executor.execute.side_effect = TFEError("rejected", error_code=TFEErrorCode.VALIDATION)
    with pytest.raises(ApplicationError) as error:
        await registry[name]({}, None)
    assert error.value.type == "VALIDATION"
    assert error.value.non_retryable is True
    assert build_tfe_activity_registry()[name] is not registry[name]


@pytest.mark.parametrize(
    ("operation", "values", "integration"),
    [
        ("get_run_status", {"wait_for_completion": True}, {}),
        ("list_workspaces", {"project_id": "prj-1"}, {}),
        ("list_runs_for_workspace", {"status": "applied"}, {}),
        ("move_workspace_to_project", {"project_id": None}, {}),
        ("create_workspace", {}, {"verify_ssl": False}),
        ("create_workspace", {}, {"ca_certificate": "PEM"}),
    ],
)
def test_unsupported_sdk_semantics_fail_explicitly(
    operation: str, values: dict[str, Any], integration: dict[str, Any]
) -> None:
    with pytest.raises(TFEError):
        sdk_inputs(operation, values, integration)


def test_variable_values_and_sensitive_state_outputs_are_not_persisted() -> None:
    result = workflow_output(
        "list_variables", {"data": [{"id": "var-1", "attributes": {"key": "key", "value": "SECRET"}}]}, {}, "acme"
    )
    assert "SECRET" not in str(result)
    state = workflow_output(
        "fetch_state_and_outputs",
        {
            "data": {"id": "sv-1"},
            "related": {
                "outputs": {
                    "data": [
                        {"attributes": {"name": "password", "sensitive": True, "value": "SECRET"}},
                        {"attributes": {"name": "public", "value": "ok"}},
                    ]
                }
            },
        },
        {},
        "acme",
    )
    assert state["outputs"] == {"public": "ok"}


# Optional cross-repository contract suite. Production imports never depend on
# the SDK checkout. CI can supply the manifests directory as a build artifact.
@pytest.mark.parametrize("node_type", sorted(TFE_STEP_BINDINGS))
def test_actual_sdk_manifest_input_compatibility(node_type: str) -> None:
    directory = os.environ.get("SYNTARA_TFE_MANIFEST_DIR")
    if not directory:
        pytest.skip("Set SYNTARA_TFE_MANIFEST_DIR to run against the SDK artifact")
    binding = TFE_STEP_BINDINGS[node_type]
    manifest = yaml.safe_load((Path(directory) / (binding.operation + ".yaml")).read_text())
    samples = {
        **BASE,
        "name": "example",
        "workspace_id": "ws-1",
        "variable_id": "var-1",
        "run_id": "run-1",
        "project_id": "prj-1",
        "team_id": "team-1",
        "installation_id": "ghain-1",
        "repository": "app",
        "branch": "main",
        "key": "key",
        "value": "secret",
        "artifact": "base64-placeholder",
        "mode": "plan-only",
        "comment": "example",
        "description": "example",
        "auto_apply": False,
    }
    fields = binding.parameters.model_fields
    values = binding.parameters.model_validate(
        {key: value for key, value in samples.items() if key in fields}
    ).model_dump()
    if binding.operation == "list_workspaces":
        values["project_id"] = None
    inputs = sdk_inputs(binding.operation, values, BASE["_resolved_integration"])
    if binding.operation == "link_vcs_to_workspace":
        inputs["repository"] = "acme/app"
    invocation = ManifestCatalog([manifest]).invocation(binding.node_name, inputs, {"token": "private-token"})
    assert invocation.node_name == binding.node_name
    assert "private-token" not in repr(invocation)


@pytest.mark.asyncio
@pytest.mark.parametrize(("outputs", "expected"), [({}, {}), ({"id": "${result.workspace_id}"}, {"id": "ws-1"})])
async def test_selected_outputs_are_preserved(outputs: dict[str, str], expected: dict[str, Any]) -> None:
    transport = RecordingTransport([response("create_workspace", {"id": "ws-1", "attributes": {"name": "demo"}})])
    executor = SDKTFEStepExecutor(ManifestCatalog([descriptor("create_workspace")]), transport)
    assert await executor.execute("tfe_create_workspace", {**BASE, "name": "demo"}, outputs) == expected


def test_remote_schema_references_are_rejected_without_network_access() -> None:
    manifest = descriptor("create_workspace")
    manifest["spec"]["inputs"]["allOf"] = [{"$ref": "https://invalid.test/schema"}]
    with pytest.raises(StepContractError, match="resolved locally"):
        ManifestCatalog([manifest]).invocation("tfe_create_workspace", {}, {})


@pytest.mark.asyncio
async def test_transport_exception_is_safe_and_non_retryable() -> None:
    transport = AsyncMock()
    transport.execute.side_effect = RuntimeError("private-token")
    executor = SDKTFEStepExecutor(ManifestCatalog([descriptor("delete_workspace")]), transport)
    with pytest.raises(TFEError) as error:
        await executor.execute("tfe_delete_workspace", {**BASE, "workspace_id": "ws-1"})
    assert error.value.error_code == TFEErrorCode.OUTCOME_UNKNOWN
    assert error.value.retryable is False
    assert "private-token" not in str(error.value)
    transport.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_manifest_timeout_interrupts_transport() -> None:
    manifest = descriptor("delete_workspace")
    manifest["spec"]["executionTimeout"] = 1

    async def stalled(_invocation: StepInvocation) -> dict[str, Any]:
        await asyncio.sleep(60)
        return {}

    transport = AsyncMock()
    transport.execute.side_effect = stalled
    executor = SDKTFEStepExecutor(ManifestCatalog([manifest]), transport)
    with pytest.raises(TFEError) as error:
        await executor.execute("tfe_delete_workspace", {**BASE, "workspace_id": "ws-1"})
    assert error.value.error_code == TFEErrorCode.OUTCOME_UNKNOWN
    transport.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_sdk_runtime_round_trip() -> None:
    """Exercise the actual sibling SDK with a mocked TFE API, without deployments."""
    directory = os.environ.get("SYNTARA_TFE_MANIFEST_DIR")
    if not directory:
        pytest.skip("Set SYNTARA_TFE_MANIFEST_DIR to run against the SDK artifact")
    manifest_dir = Path(directory)
    sdk_root = manifest_dir.parents[2]
    if not (sdk_root / "sdk-python").is_dir():
        pytest.skip("The runtime round trip also requires the SDK source checkout")
    manifest = yaml.safe_load((manifest_dir / "create_workspace.yaml").read_text())

    class LocalSDKTransport:
        async def execute(self, invocation: StepInvocation) -> dict[str, Any]:
            environment = {
                **os.environ,
                "PYTHONPATH": os.pathsep.join((str(sdk_root / "sdk-python"), str(manifest_dir.parent))),
            }
            script = """
import json, sys, httpx
from tfe_nodes.runner import invoke

def handler(request):
    assert request.url.path == "/api/v2/organizations/acme/workspaces"
    assert request.headers["authorization"] == "Bearer private-token"
    body = json.loads(request.content)
    assert body["data"]["attributes"]["execution-mode"] == "agent"
    data = {"id": "ws-runtime", "type": "workspaces", "attributes": {"name": "demo"}}
    return httpx.Response(201, json={"data": data})

result = invoke("create_workspace", json.load(sys.stdin), transport=httpx.MockTransport(handler))
print(result.model_dump_json())
"""
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script,
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(json.dumps(invocation.payload()).encode())
            assert process.returncode == 0, stderr.decode()
            assert b"private-token" not in stderr
            result: dict[str, Any] = json.loads(stdout)
            return result

    executor = SDKTFEStepExecutor(ManifestCatalog([manifest]), LocalSDKTransport())
    result = await executor.execute(
        "tfe_create_workspace", {**BASE, "name": "demo", "preset": "agent", "agent_pool_id": "apool-1"}
    )
    assert result == {"workspace_id": "ws-runtime", "workspace_name": "demo", "organization": "acme"}
