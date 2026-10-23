import { RhUiFileCodeIcon, RhUiElectricityFillIcon, RhUiPlugFillIcon, RhUiNetworkIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum } from '@syntara/contracts'
import type React from 'react'

import { RegistryNodeId } from '../../../../constants'
import { createApiActivity, createScriptActivity, useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { createSubWorkflowActivity } from '../../../../stores/workflowFactories'
import type { ActionFormData } from '../../hooks/useNodeCreation'
import { ActionNodeForm } from '../../node-forms/ActionNodeForm'
import { SubWorkflowNodeForm, type SubWorkflowFormData } from '../../node-forms/SubWorkflowNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { getDefaultNodeBaseName } from '../../utils/nodeNaming'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry, type BaseNodeFormProps } from '../NodeRegistry'

function isSubWorkflowFormData(data: ActionFormData | SubWorkflowFormData): data is SubWorkflowFormData {
  return (
    'workflow_id' in data &&
    typeof data.workflow_id === 'string' &&
    'trigger_node_id' in data &&
    typeof data.trigger_node_id === 'string' &&
    'input_mapping' in data &&
    typeof data.input_mapping === 'object' &&
    data.input_mapping !== null
  )
}

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
            formComponent: SubWorkflowNodeForm as React.ComponentType<
              BaseNodeFormProps<ActionFormData | SubWorkflowFormData> & Record<string, unknown>
            >,
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
          if (subtypeId === RegistryNodeId.SUB_WORKFLOW && isSubWorkflowFormData(data)) {
            const baseName = getDefaultNodeBaseName({
              nodeTypeId: RegistryNodeId.SUB_WORKFLOW,
              label: 'Sub-workflow',
            })
            const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
              createSubWorkflowActivity({
                id,
                name,
                workflowId: data.workflow_id,
                triggerNodeId: data.trigger_node_id,
                inputMapping: data.input_mapping,
                settings: data.settings,
              })
            )
            useWorkflowStore.getState().addActivity(activity)
            onSuccess(activityId)
            return
          }

          if (subtypeId === RegistryNodeId.SUB_WORKFLOW) {
            throw new Error('Sub-workflow configuration is incomplete.')
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
