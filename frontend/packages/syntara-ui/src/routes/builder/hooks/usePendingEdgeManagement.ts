import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { PendingEdge } from '../types'
import { getButtonEdgeId, getPendingEdgeId, getPendingTargetNodeId, getPlaceholderNodeId } from '../utils/edgeHelpers'
import { markerEnd, type EdgeType } from '../utils/workflowToGraph'

/** Adds the temporary target and edge used while the user chooses a connection target. */
export function projectPendingEdgeGraph(
  nodes: NodeType[],
  edges: EdgeType[],
  pendingEdge: PendingEdge | null,
  isInitialized: boolean
): { nodes: NodeType[]; edges: EdgeType[] } {
  const nodesWithoutPendingTargets = nodes.filter((node) => !node.id.startsWith('pending-target-'))
  const edgesWithoutPending = edges.filter((edge) => !edge.id.startsWith('pending-'))
  if (!pendingEdge || !isInitialized) {
    return { nodes: nodesWithoutPendingTargets, edges: edgesWithoutPending }
  }

  const pendingTargetId = getPendingTargetNodeId(pendingEdge.sourceNodeId)
  const pendingEdgeId = getPendingEdgeId(pendingEdge.sourceNodeId)
  const buttonEdgeId = getButtonEdgeId(pendingEdge.sourceNodeId, pendingEdge.sourceHandle)
  const sourcePlaceholderId = getPlaceholderNodeId(pendingEdge.sourceNodeId, pendingEdge.sourceHandle)
  const nodesWithoutSourcePlaceholder = nodesWithoutPendingTargets.filter((node) => node.id !== sourcePlaceholderId)
  const edgesWithoutSourceButton = edgesWithoutPending.filter((edge) => edge.id !== buttonEdgeId)

  return {
    nodes: [
      ...nodesWithoutSourcePlaceholder,
      {
        id: pendingTargetId,
        type: 'placeholder',
        position: { x: pendingEdge.x - 5, y: pendingEdge.y - 5 },
        data: {},
        draggable: false,
        selectable: false,
      } as unknown as NodeType,
    ],
    edges: [
      ...edgesWithoutSourceButton,
      {
        id: pendingEdgeId,
        source: pendingEdge.sourceNodeId,
        sourceHandle: pendingEdge.sourceHandle ?? 'source',
        target: pendingTargetId,
        targetHandle: 'target',
        type: 'default',
        selectable: false,
        markerEnd,
        data: { isPending: true, isActive: true },
      },
    ],
  }
}
