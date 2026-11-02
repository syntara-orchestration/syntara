import type { ConvergeActivity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import type { ConvergeFormData } from '../step-forms/ConvergeStepForm'
import { ConvergeStepForm } from '../step-forms/ConvergeStepForm'

type ConvergeStepDetailsProps = {
  convergeData: ConvergeActivity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}

export function ConvergeStepDetails({
  convergeData,
  nodeId,
  onClose,
  onHeaderContentChange,
}: ConvergeStepDetailsProps) {
  const { showError } = useAlerts()
  const { updateActivity } = useWorkflowStoreActions()

  const convergeConfig = (convergeData.parameters ?? {}) as {
    strategy?: string
    n_required?: number
    wait_duration?: number
  }

  const initialData: Partial<ConvergeFormData> = {
    name: convergeData.name,
    strategy: (convergeConfig.strategy as 'all' | 'any') ?? 'all',
    requiredPathCount: convergeConfig.n_required ?? 1,
    wait_duration: convergeConfig.wait_duration,
    settings: convergeData.settings,
  }

  const handleSubmit = (data: ConvergeFormData) => {
    try {
      const updatedActivity: ConvergeActivity = {
        ...convergeData,
        name: data.name,
        parameters: {
          strategy: data.strategy ?? 'all',
          ...(data.strategy === 'any' &&
            data.requiredPathCount !== undefined && { n_required: data.requiredPathCount }),
          ...(data.wait_duration !== undefined && { wait_duration: data.wait_duration }),
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
    <ConvergeStepForm initialData={initialData} onSubmit={handleSubmit} onHeaderContentChange={onHeaderContentChange} />
  )
}
