import { toReactFlowNodeId } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ValidationError } from '../builderReducer'

function applyValidationFlag(node: NodeType, hasError: boolean): NodeType {
  const currentData = node.data as Record<string, unknown>
  const current = currentData.__validationError === true
  if (hasError === current) return node
  if (hasError) {
    return { ...node, data: { ...currentData, __validationError: true } } as unknown as NodeType
  }
  const cleaned = Object.fromEntries(Object.entries(currentData).filter(([key]) => key !== '__validationError'))
  return { ...node, data: cleaned } as unknown as NodeType
}

function updateNodes(currentNodes: NodeType[], validationNodeIds: Set<string> | null): NodeType[] {
  let changed = false
  const projectedNodes = currentNodes.map((node) => {
    const projected = applyValidationFlag(node, validationNodeIds?.has(node.id) ?? false)
    if (projected !== node) changed = true
    return projected
  })
  return changed ? projectedNodes : currentNodes
}

/** Derives validation markers from workflow errors for the rendered node projection. */
export function projectValidationEnrichment(
  nodes: NodeType[],
  validationErrors: ValidationError[] | undefined,
  triggers: Array<{ id: string }>,
  isInitialized: boolean
): NodeType[] {
  if (!isInitialized) return nodes

  let validationNodeIds: Set<string> | null = null
  if (validationErrors && validationErrors.length > 0) {
    const ids = new Set<string>()
    for (const error of validationErrors) {
      if (error.nodeId) ids.add(toReactFlowNodeId(error.nodeId, triggers))
    }
    validationNodeIds = ids.size > 0 ? ids : null
  }

  return updateNodes(nodes, validationNodeIds)
}
