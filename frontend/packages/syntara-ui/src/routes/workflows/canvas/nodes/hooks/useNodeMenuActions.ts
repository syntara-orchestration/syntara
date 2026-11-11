import type { MenuNodeTypeUnion } from '../../../../../constants'
import { useNodeActions } from '../../../../../routes/builder/NodeActionsContext'

import { useCanvasMenuActions, type StepMenuAction } from './useStepMenuActions'

export type NodeMenuAction = StepMenuAction

type UseNodeMenuActionsOptions = {
  nodeId: string
  nodeType: MenuNodeTypeUnion
  triggerIndex?: number
  disabled?: boolean
  additionalActions?: NodeMenuAction[]
}

/** Compatibility wrapper for callers that still use node terminology. */
export function useNodeMenuActions(options: UseNodeMenuActionsOptions): NodeMenuAction[] {
  const { nodeType, ...stepOptions } = options
  const stepActions = useNodeActions()
  return useCanvasMenuActions({ ...stepOptions, stepCategory: nodeType, stepActions })
}
