import { RhUiInfrastructureIcon } from '@patternfly/react-icons'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { TerraformNodeForm, type TerraformNodeFormData } from '../../node-forms/TerraformNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { getDefaultNodeBaseName } from '../../utils/nodeNaming'
import { buildTFEParameters, createTFEActivity, TFE_SUBTYPE_TO_ACTIVITY_TYPE } from '../../utils/tfeHelpers'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'

const SUBTYPES = [
  { id: RegistryNodeId.TFE_CREATE_WORKSPACE, label: 'Create Workspace', description: 'Create a TFE workspace' },
  { id: RegistryNodeId.TFE_LIST_WORKSPACES, label: 'List Workspaces', description: 'List TFE workspaces' },
  { id: RegistryNodeId.TFE_UPDATE_WORKSPACE, label: 'Update Workspace', description: 'Update workspace settings' },
  { id: RegistryNodeId.TFE_DELETE_WORKSPACE, label: 'Delete Workspace', description: 'Delete a TFE workspace' },
  {
    id: RegistryNodeId.TFE_FETCH_STATE_OUTPUTS,
    label: 'Fetch State and Outputs',
    description: 'Read workspace outputs',
  },
  { id: RegistryNodeId.TFE_ADD_VARIABLE, label: 'Add Variable', description: 'Add a workspace variable' },
  { id: RegistryNodeId.TFE_LIST_VARIABLES, label: 'List Variables', description: 'List workspace variables' },
  { id: RegistryNodeId.TFE_UPDATE_VARIABLE, label: 'Update Variable', description: 'Update a workspace variable' },
  { id: RegistryNodeId.TFE_DELETE_VARIABLE, label: 'Delete Variable', description: 'Delete a workspace variable' },
  {
    id: RegistryNodeId.TFE_UPLOAD_CONFIGURATION_VERSION,
    label: 'Upload Configuration Version',
    description: 'Upload HCL configuration',
  },
  { id: RegistryNodeId.TFE_TRIGGER_RUN, label: 'Trigger Run', description: 'Start a Terraform run' },
  { id: RegistryNodeId.TFE_GET_RUN_STATUS, label: 'Get Run Status', description: 'Read run status and plan exit code' },
  { id: RegistryNodeId.TFE_APPLY_RUN, label: 'Apply Run', description: 'Apply a confirmable run' },
  { id: RegistryNodeId.TFE_DISCARD_RUN, label: 'Discard Run', description: 'Discard a run' },
  { id: RegistryNodeId.TFE_CANCEL_RUN, label: 'Cancel Run', description: 'Cancel an in-flight run' },
  { id: RegistryNodeId.TFE_FORCE_CANCEL_RUN, label: 'Force Cancel Run', description: 'Force-cancel a run' },
  { id: RegistryNodeId.TFE_LIST_RUNS, label: 'List Runs', description: 'List runs for a workspace' },
  { id: RegistryNodeId.TFE_ADD_RUN_COMMENT, label: 'Add Run Comment', description: 'Comment on a run' },
  {
    id: RegistryNodeId.TFE_LIST_GITHUB_INSTALLATIONS,
    label: 'List GitHub Installations',
    description: 'List GitHub App installations',
  },
  {
    id: RegistryNodeId.TFE_GET_GITHUB_INSTALLATION,
    label: 'Get Installation Details',
    description: 'Get GitHub App installation details',
  },
  { id: RegistryNodeId.TFE_LINK_VCS, label: 'Link VCS to Workspace', description: 'Link a GitHub repo to a workspace' },
  { id: RegistryNodeId.TFE_CREATE_PROJECT, label: 'Create Project', description: 'Create a TFE project' },
  { id: RegistryNodeId.TFE_LIST_PROJECTS, label: 'List Projects', description: 'List TFE projects' },
  { id: RegistryNodeId.TFE_GET_PROJECT, label: 'Get Project Details', description: 'Get project and team permissions' },
  { id: RegistryNodeId.TFE_UPDATE_PROJECT, label: 'Update Project', description: 'Update project settings' },
  { id: RegistryNodeId.TFE_DELETE_PROJECT, label: 'Delete Project', description: 'Delete a TFE project' },
  {
    id: RegistryNodeId.TFE_MOVE_WORKSPACE_TO_PROJECT,
    label: 'Move Workspace to Project',
    description: 'Move a workspace into a project',
  },
  {
    id: RegistryNodeId.TFE_ASSIGN_TEAM_PERMISSIONS,
    label: 'Assign Team Permissions',
    description: 'Assign team access on a project',
  },
] as const

/**
 * Register the Terraform Enterprise category with modular step subtypes.
 */
export default function registerTerraformNode() {
  NodeRegistry.register(
    createCustomNode<TerraformNodeFormData>(
      {
        id: RegistryNodeId.TERRAFORM,
        label: 'Terraform',
        icon: RhUiInfrastructureIcon,
        category: 'action',
        description: 'Manage Terraform Enterprise workspaces, runs, VCS, and projects',
        keywords: ['terraform', 'tfe', 'hcp', 'workspace', 'plan', 'apply', 'iac'],
        order: 45,
        selectionTitle: 'Select a Terraform step',
        formComponent: TerraformNodeForm,
        subtypes: SUBTYPES.map((subtype) => ({
          id: subtype.id,
          label: subtype.label,
          icon: RhUiInfrastructureIcon,
          description: subtype.description,
          formTitle: subtype.label,
          formComponent: TerraformNodeForm,
          formProps: { subtypeId: subtype.id },
        })),
      },
      (data, onSuccess, onError, subtypeId) => {
        try {
          const activityType = subtypeId ? TFE_SUBTYPE_TO_ACTIVITY_TYPE[subtypeId] : undefined
          if (!activityType || !subtypeId) {
            onError('Unknown Terraform step type')
            return
          }
          const subtype = SUBTYPES.find((entry) => entry.id === subtypeId)
          const baseName = getDefaultNodeBaseName({
            nodeTypeId: subtypeId,
            label: subtype?.label ?? 'Terraform',
          })
          const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
            createTFEActivity({
              id,
              name,
              activityType,
              parameters: buildTFEParameters(data),
            })
          )
          useWorkflowStore.getState().addActivity(activity)
          onSuccess(activityId)
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to add Terraform step')
        }
      }
    )
  )
}
