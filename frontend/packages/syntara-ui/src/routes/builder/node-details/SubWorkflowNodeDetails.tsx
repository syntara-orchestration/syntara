import type { Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { createSubWorkflowActivity } from '../../../stores/workflowFactories'
import type { SubWorkflowFormData } from '../node-forms/SubWorkflowNodeForm'
import { SubWorkflowNodeForm } from '../node-forms/SubWorkflowNodeForm'

type SubWorkflowNodeDetailsProps = {
  taskData: Activity
  nodeId: string
  onClose: () => void
  onHeaderContentChange: (content: ReactNode | null) => void
  projectId?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function buildInitialData(taskData: Activity): Partial<SubWorkflowFormData> {
  const parameters = taskData.parameters ?? {}
  const inputMapping = isRecord(parameters.input_mapping) ? parameters.input_mapping : {}

  return {
    name: taskData.name ?? '',
    workflow_id: typeof parameters.workflow_id === 'string' ? parameters.workflow_id : '',
    trigger_node_id: typeof parameters.trigger_node_id === 'string' ? parameters.trigger_node_id : '',
    input_mapping: inputMapping,
    settings: taskData.settings,
  }
}

export function SubWorkflowNodeDetails({
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
}: Readonly<SubWorkflowNodeDetailsProps>) {
  const { showError } = useAlerts()
  const { updateActivity } = useWorkflowStoreActions()

  const handleSubmit = (data: SubWorkflowFormData) => {
    try {
      updateActivity(
        nodeId,
        createSubWorkflowActivity({
          id: nodeId,
          name: data.name,
          workflowId: data.workflow_id,
          triggerNodeId: data.trigger_node_id,
          inputMapping: data.input_mapping,
          settings: data.settings,
        })
      )
      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update Sub-workflow step',
      })
    }
  }

  return (
    <SubWorkflowNodeForm
      onSubmit={handleSubmit}
      onCancel={onClose}
      initialData={buildInitialData(taskData)}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}
