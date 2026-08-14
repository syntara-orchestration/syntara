import { RhUiFileCodeIcon, RhUiElectricityFillIcon, RhUiPlugFillIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum } from '@syntara/contracts'

import { RegistryNodeId } from '../../../../constants'
import { createApiActivity, createScriptActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { ActionFormData } from '../../hooks/useNodeCreation'
import { ActionNodeForm } from '../../node-forms/ActionNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { getDefaultNodeBaseName } from '../../utils/nodeNaming'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'

/**
 * Register the Action step type
 */
export default function registerActionNode() {
  NodeRegistry.register(
    createCustomNode<ActionFormData>(
      {
        id: RegistryNodeId.ACTION,
        label: 'Action',
        icon: RhUiElectricityFillIcon,
        category: 'action',
        description: 'Execute scripts or make API calls',
        keywords: ['script', 'api', 'http', 'python', 'javascript', 'bash', 'rest'],
        order: 30,
        selectionTitle: 'Select an action node',
        subtypes: [
          {
            id: RegistryNodeId.ACTION_SCRIPT,
            label: 'Script',
            icon: RhUiFileCodeIcon,
            description: 'Execute code to manage complex conditions, calculate values, or format data.',
            formTitle: 'Configure Script Actions',
            initialData: { executor: ExecutorTypeEnum.SCRIPT },
          },
          {
            id: RegistryNodeId.ACTION_API,
            label: 'REST API',
            icon: RhUiPlugFillIcon,
            description: 'Trigger an action or retrieve data from an external source.',
            formTitle: 'Configure REST API Actions',
            initialData: { executor: ExecutorTypeEnum.HTTP_REQUEST },
          },
        ],
        formComponent: ActionNodeForm,
      },
      (data, onSuccess, onError) => {
        try {
          const baseName = getDefaultNodeBaseName({
            nodeTypeId: RegistryNodeId.ACTION,
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
