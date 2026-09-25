import type { Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { TerraformNodeForm, type TerraformNodeFormData } from '../node-forms/TerraformNodeForm'
import { buildTFEParameters } from '../utils/tfeHelpers'

type TerraformTaskDetailsProps = Readonly<{
  executor: string
  config: Record<string, unknown>
  taskData: Activity
  nodeId: string
  onClose: () => void
  onHeaderContentChange: (content: ReactNode | null) => void
  projectId?: string
}>

export function TerraformTaskDetails({
  executor,
  config,
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
}: TerraformTaskDetailsProps) {
  const { showError } = useAlerts()
  const { updateActivity } = useWorkflowStoreActions()

  const handleSubmit = (data: TerraformNodeFormData) => {
    try {
      updateActivity(nodeId, {
        ...taskData,
        name: data.name,
        parameters: buildTFEParameters(data),
      })
      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update step',
      })
    }
  }

  return (
    <TerraformNodeForm
      subtypeId={executor.replaceAll('_', '-')}
      initialData={{
        ...(config as Partial<TerraformNodeFormData>),
        name: taskData.name ?? '',
        name_field: typeof config.name === 'string' ? config.name : undefined,
      }}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}
