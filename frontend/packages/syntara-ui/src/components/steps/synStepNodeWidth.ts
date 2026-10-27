import { ExecutorTypeEnum, type TaskActivity } from '@syntara/contracts'
import type { NodeProps } from '@xyflow/react'

import { FlowNodeType } from '../../constants'
import { SEMANTIC_ZOOM_TILE_SIZE_PX } from '../../routes/workflows/canvas/semanticZoom'

export const SYN_STEP_DEFAULT_NODE_WIDTH = 240
export const SYN_STEP_WIDE_NODE_WIDTH = 360

function isWideTaskNode(nodeProps: NodeProps): boolean {
  if (nodeProps.type === FlowNodeType.GENERIC) {
    return true
  }

  if (nodeProps.type !== FlowNodeType.TASK && nodeProps.type !== FlowNodeType.TASK_REVERSED) {
    return false
  }

  const data = nodeProps.data as TaskActivity | undefined
  if (!data) return false

  if (data.type === ExecutorTypeEnum.AGENTIC) {
    return true
  }

  return false
}

export function getSynStepNodeWidth(isSemanticZoom: boolean, nodeProps: NodeProps): number {
  if (isSemanticZoom) {
    return SEMANTIC_ZOOM_TILE_SIZE_PX
  }
  if (isWideTaskNode(nodeProps)) {
    return SYN_STEP_WIDE_NODE_WIDTH
  }
  return SYN_STEP_DEFAULT_NODE_WIDTH
}
