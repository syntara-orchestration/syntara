import { EdgeHandleEnum } from '@syntara/contracts'
import { useEffect } from 'react'

import type { OnAddNodeFromEdge } from '../types'
import { markerEnd, type EdgeType } from '../utils/workflowToGraph'

type UseEdgeActiveStateOptions = {
  isInitialized: boolean
  activeEdgeId: string | null
  activeEdgeButtonNodeId: string | null
  activeEdgeButtonHandle: string | null
  onAddNodeFromEdge?: OnAddNodeFromEdge
  setEdges: React.Dispatch<React.SetStateAction<EdgeType[]>>
}

/**
 * Custom hook that manages active state for edges.
 * - Updates default and loop edges (loopBack, loopOutgoing, loopDone) with onAddNode callback, markerEnd, and isActive state
 * - Updates button edges with isActive state based on activeEdgeButtonNodeId and activeEdgeButtonHandle
 */
export function useEdgeActiveState({
  isInitialized,
  activeEdgeId,
  activeEdgeButtonNodeId,
  activeEdgeButtonHandle,
  onAddNodeFromEdge,
  setEdges,
}: UseEdgeActiveStateOptions) {
  // Ensure all default and loop edges have the onAddNode callback, markerEnd, and isActive state
  useEffect(() => {
    setEdges((currentEdges) => {
      let updated = false
      const updatedEdges = currentEdges.map((edge) => {
        // Handle default edges and all loop edge types
        if (
          edge.type === 'default' ||
          edge.type === 'loopBack' ||
          edge.type === 'loopOutgoing' ||
          edge.type === 'loopDone'
        ) {
          const needsData = !edge.data?.onAddNode
          const needsMarker = !edge.markerEnd
          const needsActiveUpdate = edge.data?.isActive !== (activeEdgeId === edge.id || edge.data?.isPending)

          if (needsData || needsMarker || needsActiveUpdate) {
            updated = true
            return {
              ...edge,
              markerEnd: edge.markerEnd ?? markerEnd,
              data: {
                ...edge.data,
                onAddNode: edge.data?.onAddNode ?? onAddNodeFromEdge,
                isActive: activeEdgeId === edge.id || edge.data?.isPending,
              },
            }
          }
        }
        return edge
      })
      return updated ? updatedEdges : currentEdges
    })
  }, [setEdges, onAddNodeFromEdge, activeEdgeId])

  // Update button edge active state when activeEdgeButtonNodeId or activeEdgeButtonHandle changes
  useEffect(() => {
    if (!isInitialized) {
      return
    }

    setEdges((currentEdges) =>
      currentEdges.map((edge) => {
        if (edge.type === 'buttonEdge' || edge.id.startsWith('button-')) {
          const nodeId = edge.source
          const dataSourceHandle = typeof edge.data?.sourceHandle === 'string' ? edge.data.sourceHandle : undefined
          const edgeHandle = dataSourceHandle ?? edge.sourceHandle ?? 'source'

          // Determine if this button edge should be active
          // For nodes with specific handles (condition: true/false, loop: done/loop, approval: approved/rejected),
          // both nodeId AND handle must match
          // For regular nodes (source handle), nodeId must match and handle should be 'source' or not specified
          const specificHandles = [
            EdgeHandleEnum.TRUE,
            EdgeHandleEnum.FALSE,
            EdgeHandleEnum.DONE,
            EdgeHandleEnum.LOOP,
            EdgeHandleEnum.APPROVED,
            EdgeHandleEnum.REJECTED,
          ] as const
          const isSpecificHandle = (specificHandles as readonly string[]).includes(edgeHandle)
          const isActive = isSpecificHandle
            ? activeEdgeButtonNodeId === nodeId && activeEdgeButtonHandle === edgeHandle
            : activeEdgeButtonNodeId === nodeId &&
              (activeEdgeButtonHandle === EdgeHandleEnum.SOURCE || !activeEdgeButtonHandle)

          return {
            ...edge,
            data: {
              ...edge.data,
              isActive,
            },
          }
        }
        return edge
      })
    )
  }, [activeEdgeButtonNodeId, activeEdgeButtonHandle, isInitialized, setEdges])
}
