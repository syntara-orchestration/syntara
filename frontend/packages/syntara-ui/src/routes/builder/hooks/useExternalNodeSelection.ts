import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

/** Applies selection from the owning view to the rendered node projection. */
export function projectExternalNodeSelection(
  nodes: NodeType[],
  selectedActivityId: string | null | undefined
): NodeType[] {
  if (selectedActivityId == null) return nodes

  let changed = false
  const projectedNodes = nodes.map((node) => {
    const definitionId = 'definitionId' in node.data ? node.data.definitionId : undefined
    const selected = node.id === selectedActivityId || definitionId === selectedActivityId
    if (node.selected === selected) return node

    changed = true
    return { ...node, selected }
  })

  return changed ? projectedNodes : nodes
}
