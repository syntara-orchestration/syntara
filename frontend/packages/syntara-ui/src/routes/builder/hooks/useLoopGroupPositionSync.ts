import { useUpdateNodeInternals } from '@xyflow/react'
import { useEffect, useRef } from 'react'

import { toPositionKey } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { collectLoopGroupPositions, getLoopGroupNodeIds } from '../utils/loopUtils'
import type { EdgeType } from '../utils/workflowToGraph'

type UseLoopGroupPositionSyncParams = {
  nodes: NodeType[]
  edges: EdgeType[]
  isInitialized: boolean
  workflowVersion: number
  triggers: Array<{ id: string }>
  updateNodePositions: (
    positions: Record<string, { x: number; y: number }>,
    options?: { markDirty?: boolean; skipTracking?: boolean }
  ) => void
}

/**
 * After workflow init, syncs loop-group node positions into the store and refreshes
 * React Flow handle geometry so loop-back edges route correctly on load/reopen.
 */
export function useLoopGroupPositionSync({
  nodes,
  edges,
  isInitialized,
  workflowVersion,
  triggers,
  updateNodePositions,
}: UseLoopGroupPositionSyncParams) {
  const updateNodeInternals = useUpdateNodeInternals()
  const syncedVersionRef = useRef<number | null>(null)

  useEffect(() => {
    if (!isInitialized) return
    if (syncedVersionRef.current === workflowVersion) return
    syncedVersionRef.current = workflowVersion

    const groupPositions = collectLoopGroupPositions(nodes, edges, (id) => toPositionKey(id, triggers))
    if (Object.keys(groupPositions).length > 0) {
      updateNodePositions(groupPositions, { skipTracking: true, markDirty: false })
    }

    const groupNodeIds = getLoopGroupNodeIds(nodes, edges)
    if (groupNodeIds.size === 0) return

    // Defer until after React Flow finishes applying restored dimensions.
    const frameId = requestAnimationFrame(() => {
      groupNodeIds.forEach((nodeId) => updateNodeInternals(nodeId))
    })
    return () => cancelAnimationFrame(frameId)
  }, [nodes, edges, isInitialized, workflowVersion, triggers, updateNodePositions, updateNodeInternals])
}
