import { RhUiFileCodeIcon, RhUiElectricityFillIcon, RhUiPlugFillIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum } from '@syntara/contracts'

import { RegistryStepId } from '../../../../constants/registryStepIds'
import {
  createApiActivity,
  createBashScriptActivity,
  createPythonScriptActivity,
  useWorkflowStore,
} from '../../../../stores/useWorkflowStore'
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
        selectionTitle: 'Select an action step',
        subtypes: [
          {
            id: RegistryStepId.ACTION_SCRIPT_PYTHON,
            label: 'Python Script',
            icon: RhUiFileCodeIcon,
            description: 'Execute Python code in an isolated container.',
            formTitle: 'Configure Python Script',
            initialData: { executor: ExecutorTypeEnum.SCRIPT_PYTHON },
          },
          {
            id: RegistryStepId.ACTION_SCRIPT_BASH,
            label: 'Bash Script',
            icon: RhUiFileCodeIcon,
            description: 'Execute Bash code in an isolated container.',
            formTitle: 'Configure Bash Script',
            initialData: { executor: ExecutorTypeEnum.SCRIPT_BASH },
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
          let label = 'Python Script'
          if (data.executor === ExecutorTypeEnum.HTTP_REQUEST) {
            label = 'REST API'
          } else if (data.executor === ExecutorTypeEnum.SCRIPT_BASH) {
            label = 'Bash Script'
          }
          const baseName = getDefaultStepBaseName({
            stepTypeId: RegistryStepId.ACTION,
            initialData: { executor: data.executor },
            label,
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
            const scriptOptions = {
              id,
              name,
              code: data.code ?? '',
              environment: data.parameters,
              affinity: data.affinity,
              executionTargetId: data.execution_target_id,
              settings: data.settings,
            }
            return data.executor === ExecutorTypeEnum.SCRIPT_BASH
              ? createBashScriptActivity(scriptOptions)
              : createPythonScriptActivity(scriptOptions)
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
