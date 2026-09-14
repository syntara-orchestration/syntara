import { useEffect, useMemo, type Dispatch, type SetStateAction } from 'react'

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
  const updated = currentNodes.map((node) => {
    const result = applyValidationFlag(node, validationNodeIds?.has(node.id) ?? false)
    if (result !== node) changed = true
    return result
  })
  return changed ? updated : currentNodes
}

export function useValidationEnrichment(
  validationErrors: ValidationError[] | undefined,
  isInitialized: boolean,
  setNodes: Dispatch<SetStateAction<NodeType[]>>
) {
  const validationNodeIds = useMemo(() => {
    if (!validationErrors || validationErrors.length === 0) return null
    const ids = new Set<string>()
    for (const err of validationErrors) {
      if (err.nodeId) ids.add(err.nodeId)
    }
    return ids.size > 0 ? ids : null
  }, [validationErrors])

  useEffect(() => {
    if (!isInitialized) return
    setNodes((currentNodes) => updateNodes(currentNodes, validationNodeIds))
  }, [validationNodeIds, isInitialized, setNodes])
}
