import type { NodeProps } from '@xyflow/react'

/** Default workflow step width on the builder canvas (all step types, including agentic). */
export const SYN_STEP_DEFAULT_NODE_WIDTH = 300

export function getSynStepNodeWidth(_isSemanticZoom: boolean, _nodeProps: NodeProps): number {
  return SYN_STEP_DEFAULT_NODE_WIDTH
}
