import type { ValueOf } from './types'

/**
 * Node type and subtype identifiers for the builder NodeRegistry (Add step panel).
 * Use these constants instead of string literals when comparing or registering registry ids.
 *
 * @example
 * import { RegistryNodeId } from '@/constants/registryNodeIds'
 *
 * if (nodeTypeId === RegistryNodeId.TRIGGER) { ... }
 * NodeRegistry.register({ id: RegistryNodeId.ACTION, ... })
 */
export const RegistryNodeId = {
  TRIGGER: 'trigger',
  TRIGGER_MANUAL: 'trigger-manual',
  TRIGGER_SCHEDULED: 'trigger-scheduled',
  TRIGGER_WEBHOOK: 'trigger-webhook',
  TRIGGER_EDA: 'trigger-eda',
  ACTION: 'action',
  ACTION_SCRIPT: 'action-script',
  ACTION_API: 'action-api',
  APPROVAL: 'approval',
  LOGIC: 'logic',
  LOGIC_CONDITION: 'logic-condition',
  LOGIC_CONVERGE: 'logic-converge',
  LOGIC_LOOP: 'logic-loop',
  LOGIC_SWITCH: 'logic-switch',
  LOGIC_WAIT: 'logic-wait',
  AGENT: 'agent',
  AAP_EXECUTION: 'aap-execution',
  AAP_JOB_TEMPLATE: 'aap-job-template',
  AAP_WORKFLOW_TEMPLATE: 'aap-workflow-template',
  TERRAFORM: 'terraform',
  TFE_CREATE_WORKSPACE: 'tfe-create-workspace',
  TFE_LIST_WORKSPACES: 'tfe-list-workspaces',
  TFE_UPDATE_WORKSPACE: 'tfe-update-workspace',
  TFE_DELETE_WORKSPACE: 'tfe-delete-workspace',
  TFE_FETCH_STATE_OUTPUTS: 'tfe-fetch-state-outputs',
  TFE_ADD_VARIABLE: 'tfe-add-variable',
  TFE_LIST_VARIABLES: 'tfe-list-variables',
  TFE_UPDATE_VARIABLE: 'tfe-update-variable',
  TFE_DELETE_VARIABLE: 'tfe-delete-variable',
  TFE_UPLOAD_CONFIGURATION_VERSION: 'tfe-upload-configuration-version',
  TFE_TRIGGER_RUN: 'tfe-trigger-run',
  TFE_GET_RUN_STATUS: 'tfe-get-run-status',
  TFE_APPLY_RUN: 'tfe-apply-run',
  TFE_DISCARD_RUN: 'tfe-discard-run',
  TFE_CANCEL_RUN: 'tfe-cancel-run',
  TFE_FORCE_CANCEL_RUN: 'tfe-force-cancel-run',
  TFE_LIST_RUNS: 'tfe-list-runs',
  TFE_ADD_RUN_COMMENT: 'tfe-add-run-comment',
  TFE_LIST_GITHUB_INSTALLATIONS: 'tfe-list-github-installations',
  TFE_GET_GITHUB_INSTALLATION: 'tfe-get-github-installation',
  TFE_LINK_VCS: 'tfe-link-vcs',
  TFE_CREATE_PROJECT: 'tfe-create-project',
  TFE_LIST_PROJECTS: 'tfe-list-projects',
  TFE_GET_PROJECT: 'tfe-get-project',
  TFE_UPDATE_PROJECT: 'tfe-update-project',
  TFE_DELETE_PROJECT: 'tfe-delete-project',
  TFE_MOVE_WORKSPACE_TO_PROJECT: 'tfe-move-workspace-to-project',
  TFE_ASSIGN_TEAM_PERMISSIONS: 'tfe-assign-team-permissions',
  GENERIC: 'generic',
} as const

/** Union of registry node id values */
export type RegistryNodeIdUnion = ValueOf<typeof RegistryNodeId>

/**
 * Set of all AAP (Ansible Automation Platform) node type IDs.
 * Use this to check if a node is any AAP variant instead of manually checking each type.
 *
 * @example
 * if (AAP_NODE_IDS.has(nodeId as RegistryNodeId)) {
 *   // Handle AAP node (custom icon, colors, etc.)
 * }
 */
export const AAP_NODE_IDS = new Set<RegistryNodeIdUnion>([
  RegistryNodeId.AAP_EXECUTION,
  RegistryNodeId.AAP_JOB_TEMPLATE,
  RegistryNodeId.AAP_WORKFLOW_TEMPLATE,
])
