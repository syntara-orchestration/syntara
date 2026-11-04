import { RhUiUserCheckIcon } from '@patternfly/react-icons'

import { RegistryStepId } from '../../../../constants'
import { createApprovalActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { ApprovalFormSubmitData } from '../../step-forms/ApprovalStepForm'
import { ApprovalStepForm } from '../../step-forms/ApprovalStepForm'
import { buildNamedActivity } from '../../utils/stepCreationHelpers'
import { getDefaultStepBaseName } from '../../utils/stepNaming'
import { StepRegistry } from '../StepRegistry'

/**
 * Register the Approval step type
 * Creates a human approval gate that pauses workflow execution until approved
 */
export default function registerApprovalStep() {
  StepRegistry.register<ApprovalFormSubmitData>({
    id: RegistryStepId.APPROVAL,
    label: 'Approval',
    icon: RhUiUserCheckIcon,
    category: 'logic',
    description: 'Wait for approval or human input before continuing',
    keywords: ['approve', 'approval', 'review', 'manual', 'gate', 'checkpoint'],
    order: 50,
    formComponent: ApprovalStepForm,
    enabled: true,
    onSubmit: (data, onSuccess, onError) => {
      try {
        // Create approval activity with workflow store helper
        const baseName = getDefaultStepBaseName({ stepTypeId: RegistryStepId.APPROVAL, label: 'Approval' })
        const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
          createApprovalActivity({
            id,
            name,
            approver_users: data.approver_users,
            approver_groups: data.approver_groups,
            prompt: data.prompt,
            fallback_decision: data.fallback_decision,
            decision_window: data.decision_window,
            settings: data.settings,
          })
        )

        // Add to workflow store
        useWorkflowStore.getState().addActivity(activity)
        onSuccess(activityId)
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Failed to add approval step')
      }
    },
  })
}
