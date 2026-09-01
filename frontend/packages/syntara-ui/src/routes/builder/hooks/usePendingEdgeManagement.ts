import { useEffect } from 'react'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { getButtonEdgeId, getPendingEdgeId, getPendingTargetNodeId, getPlaceholderNodeId } from '../utils/edgeHelpers'
import { markerEnd, type EdgeType } from '../utils/workflowToGraph'

type UsePendingEdgeManagementOptions = {
  pendingEdge: { sourceNodeId: string; sourceHandle?: string; x: number; y: number } | null
  isInitialized: boolean
  setNodes: React.Dispatch<React.SetStateAction<NodeType[]>>
  setEdges: React.Dispatch<React.SetStateAction<EdgeType[]>>
}

/**
 * Custom hook that manages pending edges when user drags from a node to the canvas.
 * - Creates a temporary edge and placeholder target node at cursor position
 * - Removes button edge from source node while pending edge is active
 * - Cleans up pending edge and restores button edge when cleared
 */
export function usePendingEdgeManagement({
  pendingEdge,
  isInitialized,
  setNodes,
  setEdges,
}: UsePendingEdgeManagementOptions) {
  useEffect(() => {
    if (pendingEdge && isInitialized) {
      const pendingNodeId = getPendingTargetNodeId(pendingEdge.sourceNodeId)
      const pendingEdgeId = getPendingEdgeId(pendingEdge.sourceNodeId)
      const buttonEdgeId = getButtonEdgeId(pendingEdge.sourceNodeId, pendingEdge.sourceHandle)
      const placeholderId = getPlaceholderNodeId(pendingEdge.sourceNodeId, pendingEdge.sourceHandle)

      setNodes((currentNodes) => {
        const withoutPendingNodes = currentNodes.filter((n) => !n.id.startsWith('pending-target-'))

        const hasNode = withoutPendingNodes.some((n) => n.id === pendingNodeId)
        if (!hasNode) {
          return [
            ...withoutPendingNodes,
            {
              id: pendingNodeId,
              type: 'placeholder',
              position: { x: pendingEdge.x - 5, y: pendingEdge.y - 5 },
              data: {},
              draggable: false,
              selectable: false,
            } as unknown as NodeType,
          ]
        }
        return withoutPendingNodes
      })

      setEdges((currentEdges) => {
        const withoutPendingEdges = currentEdges.filter((e) => !e.id.startsWith('pending-'))

        const hasEdge = withoutPendingEdges.some((e) => e.id === pendingEdgeId)

        if (!hasEdge) {
          const filteredEdges = withoutPendingEdges.filter((e) => e.id !== buttonEdgeId)
          return [
            ...filteredEdges,
            {
              id: pendingEdgeId,
              source: pendingEdge.sourceNodeId,
              sourceHandle: pendingEdge.sourceHandle ?? 'source',
              target: pendingNodeId,
              targetHandle: 'target',
              type: 'default',
              selectable: false,
              markerEnd,
              data: {
                isPending: true,
                isActive: true,
              },
            },
          ]
        }
        return withoutPendingEdges
      })

      setNodes((currentNodes) => currentNodes.filter((n) => n.id !== placeholderId))
    } else if (!pendingEdge) {
      // Clear pending nodes and edges - button edge will be recreated by useButtonEdgeMaintenance
      // First remove pending target nodes
      setNodes((currentNodes) => currentNodes.filter((n) => !n.id.startsWith('pending-target-')))
      // Then remove pending edges - this will trigger useButtonEdgeMaintenance to recreate button edges
      setEdges((currentEdges) => currentEdges.filter((e) => !e.id.startsWith('pending-')))
    }
  }, [pendingEdge, isInitialized, setNodes, setEdges])
}
