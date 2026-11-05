import { RhUiTaskIcon } from '@patternfly/react-icons'

import { RegistryStepId } from '../../../../constants'
import { createFormPromptActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { FormPromptFormSubmitData } from '../../step-forms/FormPromptNodeForm'
import { FormPromptNodeForm } from '../../step-forms/FormPromptNodeForm'
import { buildNamedActivity } from '../../utils/stepCreationHelpers'
import { getDefaultStepBaseName } from '../../utils/stepNaming'
import { StepRegistry } from '../StepRegistry'

/**
 * Register the Form (form step) step type.
 */
export default function registerFormPromptStep() {
  StepRegistry.register<FormPromptFormSubmitData>({
    id: RegistryStepId.FORM_PROMPT,
    label: 'Form',
    icon: RhUiTaskIcon,
    category: 'human_tasks',
    description: 'Pause the workflow and collect structured input from a user',
    keywords: ['form', 'prompt', 'interactive', 'input', 'human', 'survey'],
    order: 51,
    formComponent: FormPromptNodeForm,
    enabled: false,
    onSubmit: (data, onSuccess, onError) => {
      try {
        const baseName = getDefaultStepBaseName({ stepTypeId: RegistryStepId.FORM_PROMPT, label: 'Form' })
        const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
          createFormPromptActivity({
            id,
            name,
            form_definition: data.form_definition,
            message: data.message,
            responder_users: data.responder_users,
            responder_groups: data.responder_groups,
            response_window: data.response_window,
            fallback_decision: data.fallback_decision,
            submit_label: data.submit_label,
            success_message: data.success_message,
            css_override: data.css_override,
            settings: data.settings,
          })
        )

        useWorkflowStore.getState().addActivity(activity)
        onSuccess(activityId)
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Failed to add form step')
      }
    },
  })
}
