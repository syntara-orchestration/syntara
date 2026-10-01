"""Keep tfe_*.schema.json parameter fields in sync with Python TFE models."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from syntara.workflows.workflow_engine.models import tfe_types
from syntara.workflows.workflow_engine.models.tfe_types import TFEIntegrationMixin

_EXECUTOR_SCHEMA_DIR = Path(__file__).resolve().parents[5] / "src/syntara/schemas/workflows/v2/executors"

_STEM_TO_PARAMETERS: dict[str, type[TFEIntegrationMixin]] = {
    "tfe_create_workspace": tfe_types.TFECreateWorkspaceParameters,
    "tfe_list_workspaces": tfe_types.TFEListWorkspacesParameters,
    "tfe_update_workspace": tfe_types.TFEUpdateWorkspaceParameters,
    "tfe_delete_workspace": tfe_types.TFEDeleteWorkspaceParameters,
    "tfe_fetch_state_outputs": tfe_types.TFEFetchStateOutputsParameters,
    "tfe_add_variable": tfe_types.TFEAddVariableParameters,
    "tfe_list_variables": tfe_types.TFEListVariablesParameters,
    "tfe_update_variable": tfe_types.TFEUpdateVariableParameters,
    "tfe_delete_variable": tfe_types.TFEDeleteVariableParameters,
    "tfe_upload_configuration_version": tfe_types.TFEUploadConfigurationVersionParameters,
    "tfe_trigger_run": tfe_types.TFETriggerRunParameters,
    "tfe_get_run_status": tfe_types.TFEGetRunStatusParameters,
    "tfe_apply_run": tfe_types.TFERunActionParameters,
    "tfe_discard_run": tfe_types.TFERunActionParameters,
    "tfe_cancel_run": tfe_types.TFERunActionParameters,
    "tfe_force_cancel_run": tfe_types.TFERunActionParameters,
    "tfe_list_runs": tfe_types.TFEListRunsParameters,
    "tfe_add_run_comment": tfe_types.TFEAddRunCommentParameters,
    "tfe_list_github_installations": tfe_types.TFEListGitHubInstallationsParameters,
    "tfe_get_github_installation": tfe_types.TFEGetGitHubInstallationParameters,
    "tfe_link_vcs": tfe_types.TFELinkVCSParameters,
    "tfe_create_project": tfe_types.TFECreateProjectParameters,
    "tfe_list_projects": tfe_types.TFEListProjectsParameters,
    "tfe_get_project": tfe_types.TFEGetProjectParameters,
    "tfe_update_project": tfe_types.TFEUpdateProjectParameters,
    "tfe_delete_project": tfe_types.TFEDeleteProjectParameters,
    "tfe_move_workspace_to_project": tfe_types.TFEMoveWorkspaceToProjectParameters,
    "tfe_assign_team_permissions": tfe_types.TFEAssignTeamPermissionsParameters,
}

_EXPECTED_ORGANIZATION = {
    "type": ["string", "null"],
    "description": "Optional organization override; defaults to the integration organization",
}


def _schema_paths() -> list[Path]:
    return sorted(_EXECUTOR_SCHEMA_DIR.glob("tfe_*.schema.json"))


def test_all_tfe_parameter_models_have_executor_schemas() -> None:
    """Every TFE parameter model must map to a published executor schema."""
    schema_stems = {path.name.removesuffix(".schema.json") for path in _schema_paths()}
    assert schema_stems == set(_STEM_TO_PARAMETERS)


@pytest.mark.parametrize("schema_path", _schema_paths(), ids=lambda p: p.name)
def test_tfe_executor_schema_includes_integration_mixin_fields(schema_path: Path) -> None:
    """Mixin fields (integration_id, credential_id, organization) must be present and optional org shaped."""
    stem = schema_path.name.removesuffix(".schema.json")
    model = _STEM_TO_PARAMETERS[stem]
    data = json.loads(schema_path.read_text())
    properties = data["parameterSchema"]["properties"]
    required = set(data["parameterSchema"].get("required", []))

    missing = sorted(set(model.model_fields) - set(properties))
    assert missing == [], f"{schema_path.name} missing fields from {model.__name__}: {missing}"

    for field in TFEIntegrationMixin.model_fields:
        assert field in properties, f"{schema_path.name} missing mixin field {field}"

    assert properties["organization"] == _EXPECTED_ORGANIZATION
    assert "organization" not in required
    prop_keys = list(properties)
    assert prop_keys.index("organization") == prop_keys.index("credential_id") + 1
