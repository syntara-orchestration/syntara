"""Translate workflow inputs and SDK results without changing saved workflow schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.presets import workspace_preset_parts
from syntara.terraform.run_modes import map_run_mode
from syntara.workflows.workflow_engine.activities.tfe_common import data_attrs, data_id, list_resources, map_run_phase


def _validate_sdk_options(operation: str, values: dict[str, Any], integration: dict[str, Any]) -> None:
    if integration.get("verify_ssl") is False or integration.get("ca_certificate"):
        message = "SDK transport does not yet support integration-specific TLS settings"
        raise TFEError(message, error_code=TFEErrorCode.CONFIG_MISSING)
    if operation == "get_run_status" and values.get("wait_for_completion"):
        message = (
            "SDK status execution requires explicit workflow polling; use native execution for wait_for_completion"
        )
        raise TFEError(message, error_code=TFEErrorCode.VALIDATION)
    if (operation == "list_workspaces" and values.get("project_id")) or (
        operation == "list_runs_for_workspace" and values.get("status")
    ):
        message = "The SDK descriptor does not yet support this server-side list filter"
        raise TFEError(message, error_code=TFEErrorCode.VALIDATION)
    if operation == "move_workspace_to_project" and (not values.get("project_id")):
        message = "SDK project moves require an explicit project_id"
        raise TFEError(message, error_code=TFEErrorCode.VALIDATION)


def _inputs_create_workspace(result: dict[str, Any], values: dict[str, Any], operation: str) -> None:
    attrs, _ = workspace_preset_parts(
        values.get("preset"),
        agent_pool_id=values.get("agent_pool_id"),
        repository=values.get("repository"),
        branch=values.get("branch"),
        oauth_token_id=values.get("oauth_token_id"),
        github_app_installation_id=values.get("github_app_installation_id"),
        disconnect_vcs=operation == "update_workspace_settings",
    )
    for key in ("auto_apply", "terraform_version", "description", "working_directory", "execution_mode"):
        value = result.pop(key, None)
        if value is not None and (key != "execution_mode" or not values.get("preset")):
            attrs[key.replace("_", "-")] = value
    result["attributes"] = attrs


def _inputs_update_variable(result: dict[str, Any], _values: dict[str, Any], _operation: str) -> None:
    result["attributes"] = {key: result.pop(key) for key in ("value", "hcl", "category", "sensitive") if key in result}


def _inputs_list_variables(result: dict[str, Any], _values: dict[str, Any], _operation: str) -> None:
    result.pop("key", None)


def _inputs_upload_configuration_version(result: dict[str, Any], _values: dict[str, Any], _operation: str) -> None:
    result["archive_base64"] = result.pop("artifact")


def _inputs_trigger_run(result: dict[str, Any], values: dict[str, Any], _operation: str) -> None:
    result["attributes"] = map_run_mode(
        values["mode"],
        target_resources=values.get("target_resources"),
        replace_resources=values.get("replace_resources"),
        message=values.get("message"),
    )
    for key in ("mode", "target_resources", "replace_resources", "message"):
        result.pop(key, None)


def _inputs_add_run_comment(result: dict[str, Any], _values: dict[str, Any], _operation: str) -> None:
    result["body"] = result.pop("comment")


def _inputs_get_installation_details(result: dict[str, Any], values: dict[str, Any], operation: str) -> None:
    result["github_app_installation_id"] = result.pop("installation_id")
    if operation == "link_vcs_to_workspace":
        result["repository"] = values["repository"]
        result["branch"] = values["branch"]


def _inputs_update_project_settings(result: dict[str, Any], _values: dict[str, Any], _operation: str) -> None:
    result["attributes"] = {key: result.pop(key) for key in ("name", "description") if key in result}


_INPUT_MAPPERS: dict[str, Callable[[dict[str, Any], dict[str, Any], str], None]] = {
    "create_workspace": _inputs_create_workspace,
    "update_workspace_settings": _inputs_create_workspace,
    "update_variable": _inputs_update_variable,
    "list_variables": _inputs_list_variables,
    "upload_configuration_version": _inputs_upload_configuration_version,
    "trigger_run": _inputs_trigger_run,
    "add_run_comment": _inputs_add_run_comment,
    "get_installation_details": _inputs_get_installation_details,
    "link_vcs_to_workspace": _inputs_get_installation_details,
    "update_project_settings": _inputs_update_project_settings,
}


def sdk_inputs(operation: str, values: dict[str, Any], integration: dict[str, Any]) -> dict[str, Any]:
    """Translate workflow inputs while rejecting unsupported SDK semantics."""
    _validate_sdk_options(operation, values, integration)
    result = {key: value for key, value in values.items() if value is not None}
    for key in (
        "integration_id",
        "organization",
        "preset",
        "agent_pool_id",
        "repository",
        "branch",
        "oauth_token_id",
        "github_app_installation_id",
        "wait_for_completion",
        "poll_interval_seconds",
        "timeout_seconds",
    ):
        result.pop(key, None)
    result["base_url"] = integration["base_url"]
    if operation in {"create_workspace", "list_workspaces", "create_project", "list_projects"}:
        result["organization"] = values.get("organization") or integration["organization"]
    mapper = _INPUT_MAPPERS.get(operation)
    if mapper is not None:
        mapper(result, values, operation)
    return result


@dataclass(frozen=True)
class _OutputContext:
    operation: str
    result: dict[str, Any]
    values: dict[str, Any]
    organization: str

    @property
    def attrs(self) -> dict[str, Any]:
        return data_attrs({"data": self.result["data"]})

    @property
    def identifier(self) -> str | None:
        return data_id({"data": self.result["data"]})

    @property
    def resources(self) -> list[dict[str, Any]]:
        return list_resources({"data": self.result["data"]})

    @property
    def related(self) -> dict[str, Any]:
        return dict(self.result.get("related", {}))


def _output_create_workspace(context: _OutputContext) -> dict[str, Any]:
    return {
        "workspace_id": context.identifier,
        "workspace_name": context.attrs.get("name") or context.values["name"],
        "organization": context.values.get("organization") or context.organization,
    }


def _output_list_workspaces(context: _OutputContext) -> dict[str, Any]:
    items = [
        {"id": item.get("id"), "name": item.get("name"), "autoApply": item.get("auto-apply")}
        for item in context.resources
    ]
    return {"workspaces": items, "count": len(items)}


def _output_update_workspace_settings(context: _OutputContext) -> dict[str, Any]:
    return {"workspace_id": context.values["workspace_id"]}


def _output_delete_workspace(_context: _OutputContext) -> dict[str, Any]:
    return {"deleted": True}


def _output_fetch_state_and_outputs(context: _OutputContext) -> dict[str, Any]:
    outputs = {
        item["name"]: item.get("value")
        for item in list_resources(context.related.get("outputs", {}))
        if item.get("name") and (not item.get("sensitive"))
    }
    return {"has_state": context.identifier is not None, "state_version_id": context.identifier, "outputs": outputs}


def _output_add_variable(context: _OutputContext) -> dict[str, Any]:
    return {"variable_id": context.identifier if context.operation == "add_variable" else context.values["variable_id"]}


def _output_list_variables(context: _OutputContext) -> dict[str, Any]:
    items = [
        {key: item.get(key) for key in ("id", "key", "category", "sensitive", "hcl")}
        for item in context.resources
        if not context.values.get("key") or item.get("key") == context.values["key"]
    ]
    return {"variables": items, "count": len(items)}


def _output_upload_configuration_version(context: _OutputContext) -> dict[str, Any]:
    return {"configuration_version_id": context.identifier}


def _output_trigger_run(context: _OutputContext) -> dict[str, Any]:
    return {"run_id": context.identifier, "mode": context.values["mode"], "status": "pending"}


def _output_get_run_status(context: _OutputContext) -> dict[str, Any]:
    plan = data_attrs(context.related.get("plan", {}))
    actions = context.attrs.get("actions") or {}
    return {
        "run_id": context.values["run_id"],
        "status": context.attrs.get("status"),
        "phase": map_run_phase(context.attrs.get("status")),
        "has_changes": context.attrs.get("has-changes"),
        "plan_exit_code": plan.get("exit-code"),
        "resource_changes": {
            "toAdd": plan.get("resource-additions"),
            "toChange": plan.get("resource-changes"),
            "toDestroy": plan.get("resource-destructions"),
        }
        if plan
        else None,
        **{
            key.replace("-", "_"): actions.get(key)
            for key in ("is-confirmable", "is-cancelable", "is-force-cancelable")
        },
    }


def _output_apply_run(context: _OutputContext) -> dict[str, Any]:
    return {"run_id": context.values["run_id"], "action_queued": True}


def _output_list_runs_for_workspace(context: _OutputContext) -> dict[str, Any]:
    items = [
        {
            "runId": item.get("id"),
            "status": item.get("status"),
            "phase": map_run_phase(item.get("status")),
            "message": item.get("message"),
            "createdAt": item.get("created-at"),
        }
        for item in context.resources
    ]
    return {"runs": items, "count": len(items)}


def _output_add_run_comment(context: _OutputContext) -> dict[str, Any]:
    return {"comment_id": context.identifier}


def _output_list_github_installations(context: _OutputContext) -> dict[str, Any]:
    items = [
        {
            "installationId": item.get("id"),
            "owner": item.get("name") or item.get("owner"),
            "displayName": item.get("name"),
            "repositories": item.get("repository-selection"),
        }
        for item in context.resources
    ]
    return {"installations": items, "count": len(items)}


def _output_get_installation_details(context: _OutputContext) -> dict[str, Any]:
    return {
        "installation_id": context.identifier,
        "owner": context.attrs.get("name") or context.attrs.get("owner"),
        "display_name": context.attrs.get("name"),
        "repositories": context.attrs.get("repository-selection")
        if isinstance(context.attrs.get("repository-selection"), list)
        else None,
    }


def _output_link_vcs_to_workspace(context: _OutputContext) -> dict[str, Any]:
    return {"linked": True, "identifier": context.values["repository"], "branch": context.values["branch"]}


def _output_create_project(context: _OutputContext) -> dict[str, Any]:
    return {"project_id": context.identifier}


def _output_list_projects(context: _OutputContext) -> dict[str, Any]:
    items = [{"id": item.get("id"), "name": item.get("name")} for item in context.resources]
    return {"projects": items, "count": len(items)}


def _output_get_project_details(context: _OutputContext) -> dict[str, Any]:
    teams = [
        {"teamId": item.get("id"), "teamName": item.get("name"), "access": item.get("access")}
        for item in list_resources(context.related.get("team_permissions", {}))
    ]
    return {
        "project_id": context.identifier,
        "name": context.attrs.get("name"),
        "description": context.attrs.get("description"),
        "teams": teams,
    }


def _output_update_project_settings(context: _OutputContext) -> dict[str, Any]:
    return {"project_id": context.values["project_id"]}


def _output_move_workspace_to_project(context: _OutputContext) -> dict[str, Any]:
    return {"workspace_id": context.values["workspace_id"], "project_id": context.values["project_id"]}


def _output_assign_team_permissions(context: _OutputContext) -> dict[str, Any]:
    return {key: context.values[key] for key in ("project_id", "team_id", "access")}


_OUTPUT_MAPPERS: dict[str, Callable[[_OutputContext], dict[str, Any]]] = {
    "create_workspace": _output_create_workspace,
    "list_workspaces": _output_list_workspaces,
    "update_workspace_settings": _output_update_workspace_settings,
    "delete_workspace": _output_delete_workspace,
    "delete_variable": _output_delete_workspace,
    "delete_project": _output_delete_workspace,
    "fetch_state_and_outputs": _output_fetch_state_and_outputs,
    "add_variable": _output_add_variable,
    "update_variable": _output_add_variable,
    "list_variables": _output_list_variables,
    "upload_configuration_version": _output_upload_configuration_version,
    "trigger_run": _output_trigger_run,
    "get_run_status": _output_get_run_status,
    "apply_run": _output_apply_run,
    "discard_run": _output_apply_run,
    "cancel_run": _output_apply_run,
    "force_cancel_run": _output_apply_run,
    "list_runs_for_workspace": _output_list_runs_for_workspace,
    "add_run_comment": _output_add_run_comment,
    "list_github_installations": _output_list_github_installations,
    "get_installation_details": _output_get_installation_details,
    "link_vcs_to_workspace": _output_link_vcs_to_workspace,
    "create_project": _output_create_project,
    "list_projects": _output_list_projects,
    "get_project_details": _output_get_project_details,
    "update_project_settings": _output_update_project_settings,
    "move_workspace_to_project": _output_move_workspace_to_project,
    "assign_team_permissions": _output_assign_team_permissions,
}


def workflow_output(
    operation: str, result: dict[str, Any], values: dict[str, Any], organization: str
) -> dict[str, Any]:
    """Normalize SDK JSON:API resources into the existing NodeOutput fields."""
    mapper = _OUTPUT_MAPPERS.get(operation)
    if mapper is None:
        message = "Unknown TFE SDK output mapping"
        raise TFEError(message, error_code=TFEErrorCode.CONFIG_MISSING)
    return mapper(_OutputContext(operation, result, values, organization))
