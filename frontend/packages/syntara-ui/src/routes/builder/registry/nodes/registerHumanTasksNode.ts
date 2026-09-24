import { RhUiCheckClipboardIcon, RhUiUserCheckIcon } from '@patternfly/react-icons'

import { RegistryNodeId } from '../../../../constants'
import { createApprovalActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { ApprovalFormSubmitData } from '../../node-forms/ApprovalNodeForm'
import { ApprovalNodeForm } from '../../node-forms/ApprovalNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { getDefaultNodeBaseName } from '../../utils/nodeNaming'
import type { NodeTypeDefinition } from '../NodeRegistry'
import { NodeRegistry } from '../NodeRegistry'

/**
 * Register the Human tasks category (approval subtype; Form subtype added in a follow-up PR).
 */
export default function registerHumanTasksNode() {
  const definition: NodeTypeDefinition<ApprovalFormSubmitData> = {
    id: RegistryNodeId.HUMAN_TASKS,
    label: 'Human tasks',
    icon: RhUiCheckClipboardIcon,
    category: 'human_tasks',
    description: 'Pause the workflow for human approval or structured input',
    keywords: ['human', 'approval', 'manual', 'review', 'gate'],
    order: 45,
    selectionTitle: 'Select a human task step',
    formComponent: ApprovalNodeForm,
    subtypes: [
      {
        id: RegistryNodeId.APPROVAL,
        label: 'Approval',
        icon: RhUiUserCheckIcon,
        description: 'Wait for approval before continuing',
        formTitle: 'Configure Approval',
        formComponent: ApprovalNodeForm,
        order: 50,
      },
    ],
    onSubmit: (data, onSuccess, onError, subtypeId) => {
      try {
        if (subtypeId === RegistryNodeId.APPROVAL) {
          const approvalData = data
          const baseName = getDefaultNodeBaseName({ nodeTypeId: RegistryNodeId.APPROVAL, label: 'Approval' })
          const { activityId, activity } = buildNamedActivity(baseName, approvalData.name, (id, name) =>
            createApprovalActivity({
              id,
              name,
              approver_users: approvalData.approver_users,
              approver_groups: approvalData.approver_groups,
              prompt: approvalData.prompt,
              fallback_decision: approvalData.fallback_decision,
              decision_window: approvalData.decision_window,
              settings: approvalData.settings,
            })
          )
          useWorkflowStore.getState().addActivity(activity)
          onSuccess(activityId)
          return
        }

        onError('Select Approval')
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Failed to add human task step')
      }
    },
  }

  NodeRegistry.register(definition)
}
