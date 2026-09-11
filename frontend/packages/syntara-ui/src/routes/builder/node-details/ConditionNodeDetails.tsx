import type { ConditionActivity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { ConditionNodeForm } from '../node-forms/ConditionNodeForm'

type ConditionNodeDetailsProps = {
  conditionData: ConditionActivity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}

export function ConditionNodeDetails({
  conditionData,
  nodeId,
  onClose,
  onHeaderContentChange,
}: ConditionNodeDetailsProps) {
  const { showError } = useAlerts()
  // Use action accessor - component won't re-render when store state changes
  const { updateActivity } = useWorkflowStoreActions()

  // In v2, condition is at parameters.condition (not top-level condition)
  const conditionConfig = (conditionData.parameters ?? {}) as { condition?: string }

  const initialData = {
    name: conditionData.name,
    condition: conditionConfig.condition,
  }

  const handleSubmit = (data: { name: string; condition?: string }) => {
    try {
      const updatedActivity: ConditionActivity = {
        ...conditionData,
        name: data.name,
        parameters: {
          condition: data.condition ?? '',
        },
      } as ConditionActivity

      updateActivity(nodeId, updatedActivity)
      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update step',
      })
    }
  }

  return (
    <ConditionNodeForm
      initialData={initialData}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
    />
  )
}
