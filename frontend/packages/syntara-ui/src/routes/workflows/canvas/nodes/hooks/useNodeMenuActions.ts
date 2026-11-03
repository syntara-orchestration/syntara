import type { MenuNodeTypeUnion } from '../../../../../constants'
import { useNodeActions } from '../../../../../routes/builder/NodeActionsContext'

import { useCanvasMenuActions, type StepMenuAction } from './useStepMenuActions'

// Re-export for legacy callers while the canvas components migrate to step terminology.
/** @public */
export { MenuNodeType } from '../../../../../constants'

export { type MenuNodeTypeUnion, StepMenuCategory, type StepMenuCategoryUnion } from '../../../../../constants'

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
