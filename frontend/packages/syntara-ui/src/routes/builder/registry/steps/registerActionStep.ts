import { RhUiFileCodeIcon, RhUiElectricityFillIcon, RhUiPlugFillIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum } from '@syntara/contracts'

import { RegistryStepId } from '../../../../constants'
import { createApiActivity, createScriptActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { ActionStepForm } from '../../step-forms/ActionStepForm'
import type { ActionFormData } from '../../stepFormTypes'
import { buildNamedActivity } from '../../utils/stepCreationHelpers'
import { getDefaultStepBaseName } from '../../utils/stepNaming'
import { createCustomStep } from '../helpers/stepTemplates'
import { StepRegistry } from '../StepRegistry'

/**
 * Register the Action step type
 */
export default function registerActionStep() {
  StepRegistry.register(
    createCustomStep<ActionFormData>(
      {
        id: RegistryStepId.ACTION,
        label: 'Action',
        icon: RhUiElectricityFillIcon,
        category: 'action',
        description: 'Execute scripts or make API calls',
        keywords: ['script', 'api', 'http', 'python', 'javascript', 'bash', 'rest'],
        order: 30,
        selectionTitle: 'Select an action node',
        subtypes: [
          {
            id: RegistryStepId.ACTION_SCRIPT,
            label: 'Script',
            icon: RhUiFileCodeIcon,
            description: 'Execute code to manage complex conditions, calculate values, or format data.',
            formTitle: 'Configure Script Actions',
            initialData: { executor: ExecutorTypeEnum.SCRIPT },
          },
          {
            id: RegistryStepId.ACTION_API,
            label: 'REST API',
            icon: RhUiPlugFillIcon,
            description: 'Trigger an action or retrieve data from an external source.',
            formTitle: 'Configure REST API Actions',
            initialData: { executor: ExecutorTypeEnum.HTTP_REQUEST },
          },
        ],
        formComponent: ActionStepForm,
      },
      (data, onSuccess, onError) => {
        try {
          const baseName = getDefaultStepBaseName({
            stepTypeId: RegistryStepId.ACTION,
            initialData: { executor: data.executor },
            label: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? 'REST API' : 'Script',
          })
          const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) => {
            if (data.executor === ExecutorTypeEnum.HTTP_REQUEST) {
              return createApiActivity({
                id,
                name,
                method: data.method,
                url: data.url,
                headers: data.headers,
                body: data.body,
                inputs: data.parameters,
                credentialId: data.credential_id,
              })
            }
            return createScriptActivity({
              id,
              name,
              language: data.language,
              code: data.code,
              credentialId: data.credential_id,
              environment: data.parameters,
              settings: data.settings,
            })
          })

          useWorkflowStore.getState().addActivity(activity)
          onSuccess(activityId)
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to add action')
        }
      }
    )
  )
}
