import { RhUiFileCodeIcon, RhUiElectricityFillIcon, RhUiPlugFillIcon, RhUiNetworkIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum } from '@syntara/contracts'

import { RegistryNodeId } from '../../../../constants'
import {
  createApiActivity,
  createScriptActivity,
  createSubWorkflowActivity,
  useWorkflowStore,
} from '../../../../stores/useWorkflowStore'
import type { ActionFormData } from '../../hooks/useNodeCreation'
import { ActionNodeForm } from '../../node-forms/ActionNodeForm'
import { SubWorkflowNodeForm, type SubWorkflowFormData } from '../../node-forms/SubWorkflowNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { getDefaultNodeBaseName } from '../../utils/nodeNaming'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'

/**
 * Register the Action step type
 */
export default function registerActionNode() {
  NodeRegistry.register(
    createCustomNode<ActionFormData | SubWorkflowFormData>(
      {
        id: RegistryNodeId.ACTION,
        label: 'Action',
        icon: RhUiElectricityFillIcon,
        category: 'action',
        description: 'Run scripts, make API calls, or invoke another published workflow.',
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
          {
            id: RegistryNodeId.SUB_WORKFLOW,
            label: 'Sub-workflow',
            icon: RhUiNetworkIcon,
            description: 'Call another published workflow and receive its output.',
            formTitle: 'Configure Sub-workflow',
            // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-assignment
            formComponent: SubWorkflowNodeForm as any,
          },
        ],
        formComponent: ActionNodeForm,
      },
      (
        data: ActionFormData | SubWorkflowFormData,
        onSuccess: (newNodeId?: string) => void,
        onError: (error: string) => void,
        subtypeId?: string
      ) => {
        try {
          // Handle Sub-workflow subtype separately
          if (subtypeId === RegistryNodeId.SUB_WORKFLOW) {
            const baseName = getDefaultNodeBaseName({
              nodeTypeId: RegistryNodeId.SUB_WORKFLOW,
              label: 'Sub-workflow',
            })
            const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
              createSubWorkflowActivity({
                id,
                name,
              })
            )
            useWorkflowStore.getState().addActivity(activity)
            onSuccess(activityId)
            return
          }

          // Handle Script and REST API subtypes
          const actionData = data as ActionFormData
          const baseName = getDefaultNodeBaseName({
            nodeTypeId: RegistryNodeId.ACTION,
            initialData: { executor: actionData.executor },
            label: actionData.executor === ExecutorTypeEnum.HTTP_REQUEST ? 'REST API' : 'Script',
          })
          const { activityId, activity } = buildNamedActivity(baseName, actionData.name, (id, name) => {
            if (actionData.executor === ExecutorTypeEnum.HTTP_REQUEST) {
              return createApiActivity({
                id,
                name,
                method: actionData.method,
                url: actionData.url,
                headers: actionData.headers,
                body: actionData.body,
                inputs: actionData.parameters,
                credentialId: actionData.credential_id,
              })
            }
            return createScriptActivity({
              id,
              name,
              language: actionData.language,
              code: actionData.code,
              credentialId: actionData.credential_id,
              environment: actionData.parameters,
              settings: actionData.settings,
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
