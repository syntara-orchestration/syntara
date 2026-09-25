"""Temporal activities for Terraform Enterprise workflow steps."""

from __future__ import annotations

import asyncio
import base64
import time
from typing import TYPE_CHECKING, Any

import structlog
from temporalio import activity

from syntara.terraform.errors import TFEError, TFEErrorCode
from syntara.terraform.presets import workspace_preset_parts
from syntara.terraform.run_modes import map_run_mode

if TYPE_CHECKING:
    from syntara.terraform.client import TFEClient
from syntara.terraform.telemetry import (
    TF_APPLY_RUN,
    TF_ASSIGN_TEAM_PERMISSIONS,
    TF_CREATE_WORKSPACE,
    TF_DELETE_WORKSPACE,
    TF_DISCARD_RUN,
    TF_LINK_VCS,
    TF_TRIGGER_RUN,
    emit_tfe_activity,
)
from syntara.workflows.workflow_engine.activities.tfe_common import (
    build_client_from_resolution,
    data_attrs,
    data_id,
    extract_bearer_token,
    list_resources,
    map_run_phase,
    raise_as_application_error,
)
from syntara.workflows.workflow_engine.models.tfe_types import (
    TFEAddRunCommentOutput,
    TFEAddRunCommentParameters,
    TFEAddVariableOutput,
    TFEAddVariableParameters,
    TFEAssignTeamPermissionsOutput,
    TFEAssignTeamPermissionsParameters,
    TFECreateProjectOutput,
    TFECreateProjectParameters,
    TFECreateWorkspaceOutput,
    TFECreateWorkspaceParameters,
    TFEDeleteProjectOutput,
    TFEDeleteProjectParameters,
    TFEDeleteVariableOutput,
    TFEDeleteVariableParameters,
    TFEDeleteWorkspaceOutput,
    TFEDeleteWorkspaceParameters,
    TFEFetchStateOutputsOutput,
    TFEFetchStateOutputsParameters,
    TFEGetGitHubInstallationOutput,
    TFEGetGitHubInstallationParameters,
    TFEGetProjectOutput,
    TFEGetProjectParameters,
    TFEGetRunStatusOutput,
    TFEGetRunStatusParameters,
    TFELinkVCSOutput,
    TFELinkVCSParameters,
    TFEListGitHubInstallationsOutput,
    TFEListGitHubInstallationsParameters,
    TFEListProjectsOutput,
    TFEListProjectsParameters,
    TFEListRunsOutput,
    TFEListRunsParameters,
    TFEListVariablesOutput,
    TFEListVariablesParameters,
    TFEListWorkspacesOutput,
    TFEListWorkspacesParameters,
    TFEMoveWorkspaceToProjectOutput,
    TFEMoveWorkspaceToProjectParameters,
    TFERunActionOutput,
    TFERunActionParameters,
    TFETriggerRunOutput,
    TFETriggerRunParameters,
    TFEUpdateProjectOutput,
    TFEUpdateProjectParameters,
    TFEUpdateVariableOutput,
    TFEUpdateVariableParameters,
    TFEUpdateWorkspaceOutput,
    TFEUpdateWorkspaceParameters,
    TFEUploadConfigurationVersionOutput,
    TFEUploadConfigurationVersionParameters,
)
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

logger = structlog.stdlib.get_logger(__name__)

_FINAL_RUN_STATUSES = frozenset(
    {
        "applied",
        "errored",
        "canceled",
        "force_canceled",
        "discarded",
        "planned_and_finished",
    }
)


def _client_from_input(input_config: dict[str, Any], organization: str | None = None) -> TFEClient:
    """Build TFE client from activity input (resolved integration + credentials)."""
    integration = input_config.get("_resolved_integration")
    if not integration:
        msg = "Missing resolved integration; ensure integration_id is set on the step"
        raise TFEError(msg, error_code=TFEErrorCode.CONFIG_MISSING)
    credential_id = input_config.get("credential_id")
    if not credential_id:
        msg = "credential_id is required"
        raise TFEError(msg, error_code=TFEErrorCode.CONFIG_MISSING)
    token = extract_bearer_token(input_config.get("_resolved_credentials"))
    return build_client_from_resolution(integration, token, organization_override=organization)


# ── Workspace ──────────────────────────────────────────────────────────────


@activity.defn(name=ActivityName.TFE_CREATE_WORKSPACE)
async def execute_tfe_create_workspace_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a TFE workspace."""
    params = TFECreateWorkspaceParameters.model_validate(input_config)
    org = params.organization
    with emit_tfe_activity(
        TF_CREATE_WORKSPACE, organization=org or input_config.get("_resolved_integration", {}).get("organization")
    ):
        try:
            client = _client_from_input(input_config, org)
            attrs, relationships = workspace_preset_parts(
                params.preset,
                agent_pool_id=params.agent_pool_id,
                repository=params.repository,
                branch=params.branch,
                oauth_token_id=params.oauth_token_id,
                github_app_installation_id=params.github_app_installation_id,
            )
            if params.auto_apply is not None:
                attrs["auto-apply"] = params.auto_apply
            if params.preset is None and params.execution_mode is not None:
                attrs["execution-mode"] = params.execution_mode
            if params.terraform_version is not None:
                attrs["terraform-version"] = params.terraform_version
            if params.description is not None:
                attrs["description"] = params.description
            if params.working_directory is not None:
                attrs["working-directory"] = params.working_directory
            payload = await client.create_workspace(
                params.name,
                organization=org,
                attributes=attrs or None,
                project_id=params.project_id,
                relationships=relationships or None,
            )
            result = TFECreateWorkspaceOutput(
                workspace_id=data_id(payload),
                workspace_name=data_attrs(payload).get("name") or params.name,
                organization=org or client.organization,
            )
            return result.dump(outputs)
        except TFEError as exc:
            raise_as_application_error(exc)
            raise


@activity.defn(name=ActivityName.TFE_LIST_WORKSPACES)
async def execute_tfe_list_workspaces_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List TFE workspaces."""
    params = TFEListWorkspacesParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.list_workspaces(
            organization=params.organization,
            search=params.search,
            project_id=params.project_id,
        )
        workspaces = [
            {"id": w.get("id"), "name": w.get("name"), "autoApply": w.get("auto-apply")}
            for w in list_resources(payload)
        ]
        return TFEListWorkspacesOutput(workspaces=workspaces, count=len(workspaces)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_UPDATE_WORKSPACE)
async def execute_tfe_update_workspace_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Update TFE workspace settings."""
    params = TFEUpdateWorkspaceParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        attrs, relationships = workspace_preset_parts(
            params.preset,
            agent_pool_id=params.agent_pool_id,
            repository=params.repository,
            branch=params.branch,
            oauth_token_id=params.oauth_token_id,
            github_app_installation_id=params.github_app_installation_id,
            disconnect_vcs=True,
        )
        if params.auto_apply is not None:
            attrs["auto-apply"] = params.auto_apply
        if params.description is not None:
            attrs["description"] = params.description
        if params.working_directory is not None:
            attrs["working-directory"] = params.working_directory
        if params.terraform_version is not None:
            attrs["terraform-version"] = params.terraform_version
        if params.preset is None and params.execution_mode is not None:
            attrs["execution-mode"] = params.execution_mode
        await client.update_workspace(params.workspace_id, attrs, relationships=relationships or None)
        return TFEUpdateWorkspaceOutput(workspace_id=params.workspace_id).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_DELETE_WORKSPACE)
async def execute_tfe_delete_workspace_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Delete a TFE workspace."""
    params = TFEDeleteWorkspaceParameters.model_validate(input_config)
    with emit_tfe_activity(
        TF_DELETE_WORKSPACE,
        organization=params.organization or input_config.get("_resolved_integration", {}).get("organization"),
        workspace_id=params.workspace_id,
    ):
        try:
            client = _client_from_input(input_config, params.organization)
            await client.delete_workspace(params.workspace_id, force=params.force)
            return TFEDeleteWorkspaceOutput(deleted=True).dump(outputs)
        except TFEError as exc:
            raise_as_application_error(exc)
            raise


@activity.defn(name=ActivityName.TFE_FETCH_STATE_OUTPUTS)
async def execute_tfe_fetch_state_outputs_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch current state version outputs for a workspace."""
    params = TFEFetchStateOutputsParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        state = await client.get_current_state_version(params.workspace_id)
        if state is None:
            return TFEFetchStateOutputsOutput(has_state=False, state_version_id=None, outputs={}).dump(outputs)
        state_id = data_id(state)
        outputs_payload = await client.get_state_version_outputs(state_id) if state_id else {"data": []}
        output_map: dict[str, Any] = {}
        for item in list_resources(outputs_payload):
            key = item.get("name")
            if key:
                output_map[key] = item.get("value")
        return TFEFetchStateOutputsOutput(
            has_state=True,
            state_version_id=state_id,
            outputs=output_map,
        ).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


# ── Variables ──────────────────────────────────────────────────────────────


@activity.defn(name=ActivityName.TFE_ADD_VARIABLE)
async def execute_tfe_add_variable_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Add a workspace variable (sensitive values never logged)."""
    params = TFEAddVariableParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        # Do not log params.value
        payload = await client.create_variable(
            params.workspace_id,
            {
                "key": params.key,
                "value": params.value,
                "category": params.category,
                "sensitive": params.sensitive,
                "hcl": params.hcl,
            },
        )
        return TFEAddVariableOutput(variable_id=data_id(payload)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_LIST_VARIABLES)
async def execute_tfe_list_variables_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List workspace variables without values."""
    params = TFEListVariablesParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.list_variables(params.workspace_id)
        variables = []
        for item in list_resources(payload):
            if params.key and item.get("key") != params.key:
                continue
            variables.append(
                {
                    "id": item.get("id"),
                    "key": item.get("key"),
                    "category": item.get("category"),
                    "sensitive": item.get("sensitive"),
                    "hcl": item.get("hcl"),
                }
            )
        return TFEListVariablesOutput(variables=variables, count=len(variables)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_UPDATE_VARIABLE)
async def execute_tfe_update_variable_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Update a workspace variable."""
    params = TFEUpdateVariableParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        attrs: dict[str, Any] = {}
        if params.value is not None:
            attrs["value"] = params.value
        if params.hcl is not None:
            attrs["hcl"] = params.hcl
        if params.category is not None:
            attrs["category"] = params.category
        await client.update_variable(params.variable_id, attrs)
        return TFEUpdateVariableOutput(variable_id=params.variable_id).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_DELETE_VARIABLE)
async def execute_tfe_delete_variable_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Delete a workspace variable."""
    params = TFEDeleteVariableParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        await client.delete_variable(params.variable_id)
        return TFEDeleteVariableOutput(deleted=True).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


# ── Configuration ──────────────────────────────────────────────────────────


@activity.defn(name=ActivityName.TFE_UPLOAD_CONFIGURATION_VERSION)
async def execute_tfe_upload_configuration_version_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a configuration version and upload the artifact."""
    params = TFEUploadConfigurationVersionParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        try:
            content = base64.b64decode(params.artifact)
        except Exception as exc:
            msg = "Artifact is missing, unreadable, or not valid base64"
            raise TFEError(
                msg,
                error_code=TFEErrorCode.VALIDATION,
            ) from exc
        if not content:
            raise TFEError("Artifact is empty", error_code=TFEErrorCode.VALIDATION)

        cv = await client.create_configuration_version(
            params.workspace_id,
            auto_queue_runs=params.auto_queue_runs,
        )
        cv_id = data_id(cv)
        upload_url = data_attrs(cv).get("upload-url")
        if not cv_id or not upload_url:
            msg = "TFE did not return a configuration version upload URL"
            raise TFEError(
                msg,
                error_code=TFEErrorCode.TRANSIENT,
            )
        try:
            await client.upload_configuration_version(upload_url, content)
        except TFEError:
            # Do not emit configurationVersionId on failure
            raise
        return TFEUploadConfigurationVersionOutput(configuration_version_id=cv_id).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


# ── Runs ───────────────────────────────────────────────────────────────────


@activity.defn(name=ActivityName.TFE_TRIGGER_RUN)
async def execute_tfe_trigger_run_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Trigger a TFE run in the selected mode."""
    params = TFETriggerRunParameters.model_validate(input_config)
    with emit_tfe_activity(
        TF_TRIGGER_RUN,
        organization=params.organization or input_config.get("_resolved_integration", {}).get("organization"),
        workspace_id=params.workspace_id,
        mode=params.mode,
    ):
        try:
            client = _client_from_input(input_config, params.organization)
            attrs = map_run_mode(
                params.mode,
                target_resources=params.target_resources,
                replace_resources=params.replace_resources,
                message=params.message,
            )
            payload = await client.create_run(
                attrs,
                params.workspace_id,
                configuration_version_id=params.configuration_version_id,
            )
            return TFETriggerRunOutput(
                run_id=data_id(payload),
                mode=params.mode,
                status="pending",
            ).dump(outputs)
        except TFEError as exc:
            raise_as_application_error(exc)
            raise


@activity.defn(name=ActivityName.TFE_GET_RUN_STATUS)
async def execute_tfe_get_run_status_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Get run status (optionally wait for completion)."""
    params = TFEGetRunStatusParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        deadline = time.monotonic() + params.timeout_seconds
        run_payload = await client.get_run(params.run_id)

        while params.wait_for_completion:
            status = data_attrs(run_payload).get("status")
            if status in _FINAL_RUN_STATUSES:
                break
            if time.monotonic() >= deadline:
                msg = f"Timed out waiting for run {params.run_id}; last status={status}"
                raise TFEError(
                    msg,
                    error_code=TFEErrorCode.TRANSIENT,
                    details={"status": status},
                )
            await asyncio.sleep(max(1, params.poll_interval_seconds))
            activity.heartbeat({"run_id": params.run_id, "status": status})
            run_payload = await client.get_run(params.run_id)

        attrs = data_attrs(run_payload)
        status = attrs.get("status")
        actions = attrs.get("actions") or {}
        plan_exit_code = None
        resource_changes = None
        plan_rel = (run_payload.get("data") or {}).get("relationships", {}).get("plan", {}).get("data")
        if isinstance(plan_rel, dict) and plan_rel.get("id"):
            try:
                plan = await client.get_plan(plan_rel["id"])
                plan_attrs = data_attrs(plan)
                plan_exit_code = plan_attrs.get("exit-code")
                resource_changes = {
                    "toAdd": plan_attrs.get("resource-additions"),
                    "toChange": plan_attrs.get("resource-changes"),
                    "toDestroy": plan_attrs.get("resource-destructions"),
                }
            except TFEError:
                pass

        return TFEGetRunStatusOutput(
            run_id=params.run_id,
            status=status,
            phase=map_run_phase(status),
            plan_exit_code=plan_exit_code,
            has_changes=attrs.get("has-changes"),
            resource_changes=resource_changes,
            is_confirmable=actions.get("is-confirmable"),
            is_cancelable=actions.get("is-cancelable"),
            is_force_cancelable=actions.get("is-force-cancelable"),
        ).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


async def _run_control_action(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None,
    *,
    action: str,
    telemetry_activity: str | None,
    flag: str,
    fail_message: str,
) -> dict[str, Any]:
    params = TFERunActionParameters.model_validate(input_config)
    ctx = (
        emit_tfe_activity(
            telemetry_activity,
            organization=params.organization or input_config.get("_resolved_integration", {}).get("organization"),
            run_id=params.run_id,
        )
        if telemetry_activity
        else None
    )
    if ctx:
        ctx.__enter__()
    try:
        client = _client_from_input(input_config, params.organization)
        run = await client.get_run(params.run_id)
        actions = data_attrs(run).get("actions") or {}
        if not actions.get(flag):
            details: dict[str, Any] = {}
            if action == "force-cancel":
                details["force_cancel_available_at"] = data_attrs(run).get("force-cancel-available-at")
            raise TFEError(fail_message, error_code=TFEErrorCode.STATE_CONFLICT, details=details)
        method = {
            "apply": client.apply_run,
            "discard": client.discard_run,
            "cancel": client.cancel_run,
            "force-cancel": client.force_cancel_run,
        }[action]
        await method(params.run_id, params.comment)
        result = TFERunActionOutput(run_id=params.run_id, action_queued=True).dump(outputs)
        if ctx:
            ctx.__exit__(None, None, None)
        return result
    except TFEError as exc:
        if ctx:
            ctx.__exit__(type(exc), exc, exc.__traceback__)
        raise_as_application_error(exc)
        raise
    except Exception:
        if ctx:
            ctx.__exit__(*__import__("sys").exc_info())
        raise


@activity.defn(name=ActivityName.TFE_APPLY_RUN)
async def execute_tfe_apply_run_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply a confirmable run."""
    return await _run_control_action(
        input_config,
        outputs,
        action="apply",
        telemetry_activity=TF_APPLY_RUN,
        flag="is-confirmable",
        fail_message="run is not waiting for confirmation",
    )


@activity.defn(name=ActivityName.TFE_DISCARD_RUN)
async def execute_tfe_discard_run_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Discard a run."""
    return await _run_control_action(
        input_config,
        outputs,
        action="discard",
        telemetry_activity=TF_DISCARD_RUN,
        flag="is-discardable",
        fail_message="run is not in a discardable state",
    )


@activity.defn(name=ActivityName.TFE_CANCEL_RUN)
async def execute_tfe_cancel_run_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Cancel an in-flight run."""
    return await _run_control_action(
        input_config,
        outputs,
        action="cancel",
        telemetry_activity=None,
        flag="is-cancelable",
        fail_message="run is not in-flight",
    )


@activity.defn(name=ActivityName.TFE_FORCE_CANCEL_RUN)
async def execute_tfe_force_cancel_run_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Force-cancel a run after cool-off."""
    return await _run_control_action(
        input_config,
        outputs,
        action="force-cancel",
        telemetry_activity=None,
        flag="is-force-cancelable",
        fail_message="force-cancel is not yet available for this run",
    )


@activity.defn(name=ActivityName.TFE_LIST_RUNS)
async def execute_tfe_list_runs_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List runs for a workspace."""
    params = TFEListRunsParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.list_runs(params.workspace_id, status=params.status)
        runs = [
            {
                "runId": r.get("id"),
                "status": r.get("status"),
                "phase": map_run_phase(r.get("status")),
                "message": r.get("message"),
                "createdAt": r.get("created-at"),
            }
            for r in list_resources(payload)
        ]
        return TFEListRunsOutput(runs=runs, count=len(runs)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_ADD_RUN_COMMENT)
async def execute_tfe_add_run_comment_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Add a comment to a run."""
    params = TFEAddRunCommentParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.add_run_comment(params.run_id, params.comment)
        return TFEAddRunCommentOutput(comment_id=data_id(payload)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


# ── VCS ────────────────────────────────────────────────────────────────────


@activity.defn(name=ActivityName.TFE_LIST_GITHUB_INSTALLATIONS)
async def execute_tfe_list_github_installations_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List GitHub App installations."""
    params = TFEListGitHubInstallationsParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.list_github_app_installations()
        installations = [
            {
                "installationId": i.get("id"),
                "owner": i.get("name") or i.get("owner"),
                "displayName": i.get("name"),
                "repositories": i.get("repository-selection"),
            }
            for i in list_resources(payload)
        ]
        return TFEListGitHubInstallationsOutput(installations=installations, count=len(installations)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_GET_GITHUB_INSTALLATION)
async def execute_tfe_get_github_installation_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Get GitHub App installation details."""
    params = TFEGetGitHubInstallationParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.get_github_app_installation(params.installation_id)
        attrs = data_attrs(payload)
        return TFEGetGitHubInstallationOutput(
            installation_id=data_id(payload),
            owner=attrs.get("name") or attrs.get("owner"),
            display_name=attrs.get("name"),
            repositories=attrs.get("repository-selection")
            if isinstance(attrs.get("repository-selection"), list)
            else None,
        ).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_LINK_VCS)
async def execute_tfe_link_vcs_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Link a GitHub App installation repository to a workspace."""
    params = TFELinkVCSParameters.model_validate(input_config)
    with emit_tfe_activity(
        TF_LINK_VCS,
        organization=params.organization or input_config.get("_resolved_integration", {}).get("organization"),
        workspace_id=params.workspace_id,
    ):
        try:
            client = _client_from_input(input_config, params.organization)
            installation = await client.get_github_app_installation(params.installation_id)
            owner = data_attrs(installation).get("name") or data_attrs(installation).get("owner")
            if not owner:
                raise TFEError(
                    f"GitHub installation '{params.installation_id}' has no owner",
                    error_code=TFEErrorCode.NOT_FOUND,
                )
            identifier = f"{owner}/{params.repository}"
            await client.link_vcs_to_workspace(
                params.workspace_id,
                identifier=identifier,
                branch=params.branch,
                github_app_installation_id=params.installation_id,
            )
            return TFELinkVCSOutput(linked=True, identifier=identifier, branch=params.branch).dump(outputs)
        except TFEError as exc:
            raise_as_application_error(exc)
            raise


# ── Projects ───────────────────────────────────────────────────────────────


@activity.defn(name=ActivityName.TFE_CREATE_PROJECT)
async def execute_tfe_create_project_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a TFE project."""
    params = TFECreateProjectParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.create_project(
            params.name,
            organization=params.organization,
            description=params.description,
        )
        return TFECreateProjectOutput(project_id=data_id(payload)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_LIST_PROJECTS)
async def execute_tfe_list_projects_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List TFE projects."""
    params = TFEListProjectsParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        payload = await client.list_projects(organization=params.organization)
        projects = [{"id": p.get("id"), "name": p.get("name")} for p in list_resources(payload)]
        return TFEListProjectsOutput(projects=projects, count=len(projects)).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_GET_PROJECT)
async def execute_tfe_get_project_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Get project details including team permissions."""
    params = TFEGetProjectParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        project = await client.get_project(params.project_id)
        teams_payload = await client.list_project_teams(params.project_id)
        teams = [
            {
                "teamId": t.get("id"),
                "teamName": t.get("name"),
                "access": t.get("access"),
            }
            for t in list_resources(teams_payload)
        ]
        attrs = data_attrs(project)
        return TFEGetProjectOutput(
            project_id=data_id(project),
            name=attrs.get("name"),
            description=attrs.get("description"),
            teams=teams,
        ).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_UPDATE_PROJECT)
async def execute_tfe_update_project_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Update project settings."""
    params = TFEUpdateProjectParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        attrs: dict[str, Any] = {}
        if params.name is not None:
            attrs["name"] = params.name
        if params.description is not None:
            attrs["description"] = params.description
        await client.update_project(params.project_id, attrs)
        return TFEUpdateProjectOutput(project_id=params.project_id).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_DELETE_PROJECT)
async def execute_tfe_delete_project_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Delete a TFE project."""
    params = TFEDeleteProjectParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        await client.delete_project(params.project_id)
        return TFEDeleteProjectOutput(deleted=True).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_MOVE_WORKSPACE_TO_PROJECT)
async def execute_tfe_move_workspace_to_project_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Move a workspace into a project."""
    params = TFEMoveWorkspaceToProjectParameters.model_validate(input_config)
    try:
        client = _client_from_input(input_config, params.organization)
        await client.move_workspace_to_project(params.workspace_id, params.project_id)
        return TFEMoveWorkspaceToProjectOutput(
            workspace_id=params.workspace_id,
            project_id=params.project_id,
        ).dump(outputs)
    except TFEError as exc:
        raise_as_application_error(exc)
        raise


@activity.defn(name=ActivityName.TFE_ASSIGN_TEAM_PERMISSIONS)
async def execute_tfe_assign_team_permissions_activity(
    input_config: dict[str, Any],
    outputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assign team permissions on a project."""
    params = TFEAssignTeamPermissionsParameters.model_validate(input_config)
    with emit_tfe_activity(
        TF_ASSIGN_TEAM_PERMISSIONS,
        organization=params.organization or input_config.get("_resolved_integration", {}).get("organization"),
        project_id=params.project_id,
        team_id=params.team_id,
    ):
        try:
            client = _client_from_input(input_config, params.organization)
            await client.assign_team_permissions(params.project_id, params.team_id, params.access)
            return TFEAssignTeamPermissionsOutput(
                project_id=params.project_id,
                team_id=params.team_id,
                access=params.access,
            ).dump(outputs)
        except TFEError as exc:
            raise_as_application_error(exc)
            raise


TFE_ACTIVITIES = [
    execute_tfe_create_workspace_activity,
    execute_tfe_list_workspaces_activity,
    execute_tfe_update_workspace_activity,
    execute_tfe_delete_workspace_activity,
    execute_tfe_fetch_state_outputs_activity,
    execute_tfe_add_variable_activity,
    execute_tfe_list_variables_activity,
    execute_tfe_update_variable_activity,
    execute_tfe_delete_variable_activity,
    execute_tfe_upload_configuration_version_activity,
    execute_tfe_trigger_run_activity,
    execute_tfe_get_run_status_activity,
    execute_tfe_apply_run_activity,
    execute_tfe_discard_run_activity,
    execute_tfe_cancel_run_activity,
    execute_tfe_force_cancel_run_activity,
    execute_tfe_list_runs_activity,
    execute_tfe_add_run_comment_activity,
    execute_tfe_list_github_installations_activity,
    execute_tfe_get_github_installation_activity,
    execute_tfe_link_vcs_activity,
    execute_tfe_create_project_activity,
    execute_tfe_list_projects_activity,
    execute_tfe_get_project_activity,
    execute_tfe_update_project_activity,
    execute_tfe_delete_project_activity,
    execute_tfe_move_workspace_to_project_activity,
    execute_tfe_assign_team_permissions_activity,
]
