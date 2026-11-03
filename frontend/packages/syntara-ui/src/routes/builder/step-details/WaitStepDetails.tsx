import type { WaitActivity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { useMaxWaitDuration } from '../step-forms/useMaxWaitDuration'
import { WaitStepForm, type WaitFormData } from '../step-forms/WaitStepForm'

type WaitStepDetailsProps = {
  waitData: WaitActivity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}

export function WaitStepDetails({ waitData, nodeId, onClose, onHeaderContentChange }: Readonly<WaitStepDetailsProps>) {
  const { showError } = useAlerts()
  const { updateActivity } = useWorkflowStoreActions()
  const { maxSeconds } = useMaxWaitDuration()

  const totalStoredSeconds = (waitData.parameters as { duration?: number } | undefined)?.duration ?? 0

  const initialData: Partial<WaitFormData> = {
    name: waitData.name,
    duration: totalStoredSeconds > 0 ? totalStoredSeconds : undefined,
    settings: waitData.settings,
  }

  const handleSubmit = (data: WaitFormData) => {
    try {
      const totalSeconds = data.duration ?? 0
      if (totalSeconds > maxSeconds) {
        showError({
          title: 'Cannot save wait node',
          description: `Wait duration (${totalSeconds}s) exceeds maximum allowed (${maxSeconds}s)`,
        })
        return
      }

      const updatedActivity: WaitActivity = {
        ...waitData,
        name: data.name,
        parameters: {
          duration: totalSeconds,
        },
        settings: data.settings,
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
    <WaitStepForm
      key={maxSeconds}
      initialData={initialData}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
    />
  )
}
