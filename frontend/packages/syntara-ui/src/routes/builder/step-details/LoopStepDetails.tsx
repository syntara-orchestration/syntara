import type { LoopActivity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import type { LoopFormData } from '../step-forms/LoopStepForm'
import { LoopStepForm } from '../step-forms/LoopStepForm'

type LoopStepDetailsProps = {
  loopData: LoopActivity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}

export function LoopStepDetails({ loopData, nodeId, onClose, onHeaderContentChange }: LoopStepDetailsProps) {
  const { showError } = useAlerts()
  // Use action accessor - component won't re-render when store state changes
  const { updateActivity } = useWorkflowStoreActions()

  // In v2, loop parameters are at activity.parameters (not activity.loop)
  const loopConfig = (loopData.parameters ?? {}) as {
    type?: string
    items?: string
    condition?: string
    max_iterations?: number
    maxIterations?: number
    indexVariable?: string
    itemVariable?: string
  }

  // Preserve the original loop type to avoid losing 'while' vs 'do_while' distinction
  const originalLoopType = loopConfig.type

  // Handle v2 loop types: 'for_each'/'forEach' and 'while'/'do_while'
  // Map to UI types: 'forEach' and 'while'
  const loopType: 'forEach' | 'while' =
    loopConfig.type === 'for_each' || loopConfig.type === 'forEach' ? 'forEach' : 'while'

  const maxIterations = loopConfig.max_iterations ?? loopConfig.maxIterations

  const initialData = {
    name: loopData.name,
    type: loopType,
    items: loopType === 'forEach' ? loopConfig.items : undefined,
    condition: loopType === 'while' ? loopConfig.condition : undefined,
    maxIterations,
    indexVariable: loopType === 'forEach' ? loopConfig.indexVariable : undefined,
    itemVariable: loopType === 'forEach' ? loopConfig.itemVariable : undefined,
    settings: loopData.settings,
  }

  // Determine config type preserving original backend type when possible
  const determineConfigType = (selectedType: string): string => {
    if (selectedType === 'forEach') {
      return originalLoopType === 'forEach' || originalLoopType === 'for_each' ? originalLoopType : 'for_each'
    }

    // User selected while - preserve 'while' or 'do_while' or default to 'while'
    if (originalLoopType === 'while' || originalLoopType === 'do_while') {
      return originalLoopType
    }

    return 'while'
  }

  const validMaxIterations = (value: number | undefined) =>
    typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : undefined

  const buildForEachConfig = (data: {
    items?: string
    maxIterations?: number
    indexVariable?: string
    itemVariable?: string
  }) => ({
    items: data.items ?? '',
    ...(data.indexVariable && { indexVariable: data.indexVariable }),
    ...(data.itemVariable && { itemVariable: data.itemVariable }),
    ...(validMaxIterations(data.maxIterations) !== undefined && {
      max_iterations: validMaxIterations(data.maxIterations),
    }),
    condition: undefined,
  })

  const buildWhileConfig = (data: { condition?: string; maxIterations?: number }) => ({
    condition: data.condition ?? '',
    ...(validMaxIterations(data.maxIterations) !== undefined && {
      max_iterations: validMaxIterations(data.maxIterations),
    }),
    items: undefined,
    indexVariable: undefined,
    itemVariable: undefined,
  })

  const cleanUndefinedFields = (obj: Record<string, unknown>): void => {
    Object.keys(obj).forEach((key) => {
      if (obj[key] === undefined) {
        delete obj[key]
      }
    })
  }

  const handleSubmit = (data: LoopFormData) => {
    try {
      if (!data.type || (data.type !== 'forEach' && data.type !== 'while')) {
        throw new Error('Invalid loop type')
      }

      const configType = determineConfigType(data.type)
      const typeSpecificConfig = data.type === 'forEach' ? buildForEachConfig(data) : buildWhileConfig(data)

      const config: Record<string, unknown> = {
        ...loopConfig,
        type: configType,
        ...typeSpecificConfig,
      }

      cleanUndefinedFields(config)

      const updatedActivity: LoopActivity = {
        ...loopData,
        name: data.name,
        parameters: config,
        settings: data.settings,
      } as LoopActivity

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
    <LoopStepForm initialData={initialData} onSubmit={handleSubmit} onHeaderContentChange={onHeaderContentChange} />
  )
}
