import type { Node } from '@xyflow/react'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { IconDescriptor } from '../../workflows/canvas/nodes/stepIconResolver'
import { getCanvasStepIconDescriptor } from '../../workflows/canvas/nodes/stepIconResolver'
import { StepRegistry } from '../registry/StepRegistry'

/**
 * Use this when you only have a registry step type/subtype id (Add step panel flow).
 */
export function resolveIconForType({
  stepTypeId,
  stepSubtypeId,
}: {
  stepTypeId?: string | null
  stepSubtypeId?: string | null
}): IconDescriptor {
  const iconId = stepSubtypeId ?? stepTypeId ?? undefined
  if (!iconId) return { icon: undefined, id: undefined }

  const steps = StepRegistry.getAll()
  for (const stepDefinition of steps) {
    if (stepDefinition.id === iconId) return { icon: stepDefinition.icon, id: iconId }
    const subtype = stepDefinition.subtypes?.find((item) => item.id === iconId)
    if (subtype) return { icon: subtype.icon, id: iconId }
  }

  return { icon: undefined, id: iconId }
}

/**
 * Use this when you have a runtime step instance (edit step flow).
 */
export function resolveIconForStep(
  node: Node<NodeType['data']>,
  currentWorkflow?: { triggers?: Array<{ type?: string }> } | null
): IconDescriptor {
  return getCanvasStepIconDescriptor(node, currentWorkflow)
}
