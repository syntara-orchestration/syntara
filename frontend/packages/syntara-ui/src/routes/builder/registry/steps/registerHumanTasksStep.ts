import { RhUiCheckClipboardIcon, RhUiTaskIcon, RhUiUserCheckIcon } from '@patternfly/react-icons'

import { RegistryStepId } from '../../../../constants'
import { createApprovalActivity, createFormPromptActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { ApprovalFormSubmitData } from '../../step-forms/ApprovalStepForm'
import { ApprovalStepForm } from '../../step-forms/ApprovalStepForm'
import type { FormPromptFormSubmitData } from '../../step-forms/FormPromptNodeForm'
import { FormPromptNodeForm } from '../../step-forms/FormPromptNodeForm'
import { buildNamedActivity } from '../../utils/stepCreationHelpers'
import { getDefaultStepBaseName } from '../../utils/stepNaming'
import type { StepTypeDefinition } from '../StepRegistry'
import { StepRegistry } from '../StepRegistry'

type HumanTaskFormData = ApprovalFormSubmitData | FormPromptFormSubmitData

/**
 * Register the Human tasks category (approval and form prompt subtypes).
 */
export default function registerHumanTasksStep() {
  const definition: StepTypeDefinition<HumanTaskFormData> = {
    id: RegistryStepId.HUMAN_TASKS,
    label: 'Human tasks',
    icon: RhUiCheckClipboardIcon,
    category: 'human_tasks',
    description: 'Pause the workflow for human approval or structured input',
    keywords: ['human', 'approval', 'form', 'prompt', 'manual', 'review', 'input', 'survey'],
    order: 45,
    selectionTitle: 'Select a human task step',
    formComponent: ApprovalStepForm as StepTypeDefinition<HumanTaskFormData>['formComponent'],
    subtypes: [
      {
        id: RegistryStepId.APPROVAL,
        label: 'Approval',
        icon: RhUiUserCheckIcon,
        description: 'Wait for approval before continuing',
        formTitle: 'Configure Approval',
        formComponent: ApprovalStepForm as StepTypeDefinition<HumanTaskFormData>['formComponent'],
        order: 50,
      },
      {
        id: RegistryStepId.FORM_PROMPT,
        label: 'Form',
        icon: RhUiTaskIcon,
        description: 'Pause the workflow and collect structured input from a user',
        formTitle: 'Configure Form',
        formComponent: FormPromptNodeForm as StepTypeDefinition<HumanTaskFormData>['formComponent'],
        order: 51,
      },
    ],
    onSubmit: (data, onSuccess, onError, subtypeId) => {
      try {
        if (subtypeId === RegistryStepId.APPROVAL) {
          const approvalData = data as ApprovalFormSubmitData
          const baseName = getDefaultStepBaseName({ stepTypeId: RegistryStepId.APPROVAL, label: 'Approval' })
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

        if (subtypeId === RegistryStepId.FORM_PROMPT) {
          const formData = data as FormPromptFormSubmitData
          const baseName = getDefaultStepBaseName({ stepTypeId: RegistryStepId.FORM_PROMPT, label: 'Form' })
          const { activityId, activity } = buildNamedActivity(baseName, formData.name, (id, name) =>
            createFormPromptActivity({
              id,
              name,
              form_definition: formData.form_definition,
              message: formData.message,
              responder_users: formData.responder_users,
              responder_groups: formData.responder_groups,
              response_window: formData.response_window,
              fallback_decision: formData.fallback_decision,
              submit_label: formData.submit_label,
              success_message: formData.success_message,
              css_override: formData.css_override,
              settings: formData.settings,
            })
          )
          useWorkflowStore.getState().addActivity(activity)
          onSuccess(activityId)
          return
        }

        onError('Select Approval or Form')
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Failed to add human task step')
      }
    },
  }

  StepRegistry.register(definition)
}
