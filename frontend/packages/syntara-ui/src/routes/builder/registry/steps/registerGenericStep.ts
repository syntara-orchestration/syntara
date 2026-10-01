import { RhUiAddCircleFillIcon } from '@patternfly/react-icons'

import { RegistryStepId } from '../../../../constants'
import { createGenericActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { GenericStepForm } from '../../step-forms/GenericStepForm'
import { buildNamedActivity } from '../../utils/stepCreationHelpers'
import { StepRegistry } from '../StepRegistry'

/**
 * Register the Generic placeholder step type
 * This step type is used internally (e.g., for loop bodies) but is not shown in the AddStepPanel
 * Users cannot manually add this step - it's only created programmatically
 */
export default function registerGenericStep() {
  StepRegistry.register({
    id: RegistryStepId.GENERIC,
    label: 'Generic Step',
    icon: RhUiAddCircleFillIcon,
    category: 'other',
    description: 'Placeholder step — click to configure',
    keywords: ['placeholder', 'generic', 'new', 'configure'],
    order: 1000, // High order to appear last in lists
    enabled: false, // Hide from AddStepPanel - only used programmatically
    formComponent: GenericStepForm,
    onSubmit: (_data, onSuccess, onError) => {
      try {
        // Create generic placeholder activity
        const { activityId, activity } = buildNamedActivity('Generic Step', undefined, (id, name) =>
          createGenericActivity(id, name)
        )

        useWorkflowStore.getState().addActivity(activity)
        onSuccess(activityId)
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Failed to add generic step')
      }
    },
  })
}
