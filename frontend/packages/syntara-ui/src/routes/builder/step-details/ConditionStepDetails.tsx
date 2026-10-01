import type { ConditionActivity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { ConditionStepForm } from '../step-forms/ConditionStepForm'

type ConditionStepDetailsProps = {
  conditionData: ConditionActivity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}

export function ConditionStepDetails({
  conditionData,
  nodeId,
  onClose,
  onHeaderContentChange,
}: ConditionStepDetailsProps) {
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
      }

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
    <ConditionStepForm
      initialData={initialData}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
    />
  )
}
