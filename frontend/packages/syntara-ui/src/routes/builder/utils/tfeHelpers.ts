import { ActivityTypeEnum, type Activity } from '@syntara/contracts'

import type { TerraformNodeFormData } from '../node-forms/TerraformNodeForm'

/** Map registry subtype id → backend ActivityTypeEnum value */
export const TFE_SUBTYPE_TO_ACTIVITY_TYPE: Record<string, string> = {
  'tfe-create-workspace': ActivityTypeEnum.TFE_CREATE_WORKSPACE,
  'tfe-list-workspaces': ActivityTypeEnum.TFE_LIST_WORKSPACES,
  'tfe-update-workspace': ActivityTypeEnum.TFE_UPDATE_WORKSPACE,
  'tfe-delete-workspace': ActivityTypeEnum.TFE_DELETE_WORKSPACE,
  'tfe-fetch-state-outputs': ActivityTypeEnum.TFE_FETCH_STATE_OUTPUTS,
  'tfe-add-variable': ActivityTypeEnum.TFE_ADD_VARIABLE,
  'tfe-list-variables': ActivityTypeEnum.TFE_LIST_VARIABLES,
  'tfe-update-variable': ActivityTypeEnum.TFE_UPDATE_VARIABLE,
  'tfe-delete-variable': ActivityTypeEnum.TFE_DELETE_VARIABLE,
  'tfe-upload-configuration-version': ActivityTypeEnum.TFE_UPLOAD_CONFIGURATION_VERSION,
  'tfe-trigger-run': ActivityTypeEnum.TFE_TRIGGER_RUN,
  'tfe-get-run-status': ActivityTypeEnum.TFE_GET_RUN_STATUS,
  'tfe-apply-run': ActivityTypeEnum.TFE_APPLY_RUN,
  'tfe-discard-run': ActivityTypeEnum.TFE_DISCARD_RUN,
  'tfe-cancel-run': ActivityTypeEnum.TFE_CANCEL_RUN,
  'tfe-force-cancel-run': ActivityTypeEnum.TFE_FORCE_CANCEL_RUN,
  'tfe-list-runs': ActivityTypeEnum.TFE_LIST_RUNS,
  'tfe-add-run-comment': ActivityTypeEnum.TFE_ADD_RUN_COMMENT,
  'tfe-list-github-installations': ActivityTypeEnum.TFE_LIST_GITHUB_INSTALLATIONS,
  'tfe-get-github-installation': ActivityTypeEnum.TFE_GET_GITHUB_INSTALLATION,
  'tfe-link-vcs': ActivityTypeEnum.TFE_LINK_VCS,
  'tfe-create-project': ActivityTypeEnum.TFE_CREATE_PROJECT,
  'tfe-list-projects': ActivityTypeEnum.TFE_LIST_PROJECTS,
  'tfe-get-project': ActivityTypeEnum.TFE_GET_PROJECT,
  'tfe-update-project': ActivityTypeEnum.TFE_UPDATE_PROJECT,
  'tfe-delete-project': ActivityTypeEnum.TFE_DELETE_PROJECT,
  'tfe-move-workspace-to-project': ActivityTypeEnum.TFE_MOVE_WORKSPACE_TO_PROJECT,
  'tfe-assign-team-permissions': ActivityTypeEnum.TFE_ASSIGN_TEAM_PERMISSIONS,
}

function splitCsv(value: string | undefined): string[] | undefined {
  if (!value?.trim()) return undefined
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

const DIRECT_STRING_FIELDS = [
  'integration_id',
  'credential_id',
  'organization',
  'workspace_id',
  'variable_id',
  'key',
  'value',
  'category',
  'mode',
  'run_id',
  'artifact',
  'installation_id',
  'repository',
  'branch',
  'project_id',
  'team_id',
  'access',
  'description',
  'search',
  'configuration_version_id',
  'terraform_version',
  'execution_mode',
  'preset',
  'agent_pool_id',
  'oauth_token_id',
  'github_app_installation_id',
] as const satisfies readonly (keyof TerraformNodeFormData)[]

const BOOLEAN_FIELDS = [
  'sensitive',
  'hcl',
  'force',
  'wait_for_completion',
  'auto_apply',
] as const satisfies readonly (keyof TerraformNodeFormData)[]

function copyPresentStrings(
  params: Record<string, unknown>,
  data: TerraformNodeFormData,
  keys: readonly (keyof TerraformNodeFormData)[]
): void {
  for (const key of keys) {
    const value = data[key]
    if (typeof value === 'string' && value !== '') params[key] = value
  }
}

function copyDefinedBooleans(
  params: Record<string, unknown>,
  data: TerraformNodeFormData,
  keys: readonly (keyof TerraformNodeFormData)[]
): void {
  for (const key of keys) {
    const value = data[key]
    if (typeof value === 'boolean') params[key] = value
  }
}

function assignCsvList(params: Record<string, unknown>, key: string, value: string | undefined): void {
  const items = splitCsv(value)
  if (items) params[key] = items
}

/** Build activity parameters from Terraform form data for a given subtype. */
export function buildTFEParameters(data: TerraformNodeFormData): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  copyPresentStrings(params, data, DIRECT_STRING_FIELDS)
  copyDefinedBooleans(params, data, BOOLEAN_FIELDS)
  if (data.name_field) params.name = data.name_field
  if (data.comment) {
    params.comment = data.comment
    params.message = data.comment
  }
  assignCsvList(params, 'target_resources', data.target_resources)
  assignCsvList(params, 'replace_resources', data.replace_resources)
  return params
}

export function createTFEActivity(options: {
  id: string
  name: string
  activityType: string
  parameters: Record<string, unknown>
}): Activity {
  return {
    id: options.id,
    type: options.activityType,
    name: options.name,
    parameters: options.parameters,
  }
}
