/**
 * Inserts an embedded (design-time copied) subgraph into the current workflow as a
 * single undoable operation (SDP R12).
 *
 * The caller computes the copy with copyWorkflowGraph() (so the confirmation dialog can
 * preview counts, excluded triggers, resource references and sub-workflow references first);
 * this hook performs the atomic store insertion. Ordinary copied steps execute as parent
 * steps; a copied sub_workflow step keeps its reference and runs the referenced workflow as a
 * child (Used-By applies). No reference to the source workflow is introduced.
 */
import { useCallback } from 'react'

import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { useWorkflowStoreActions } from '../../stores/workflowStoreSelectors'

import type { CopyWorkflowGraphResult } from './utils/embed/copyWorkflowGraph'

/** Horizontal gap (px) between existing nodes and the embedded graph. */
const PLACEMENT_GAP = 120

/**
 * Shift the copied positions so the embedded graph sits clear of existing nodes
 * (placed to the right, top-aligned), instead of a blind fixed offset that can stack
 * copied nodes on top of the current canvas. The internal layout is preserved.
 */
function placeClearOfExisting(
  copied: Record<string, { x: number; y: number }>,
  existing: Record<string, { x: number; y: number }>
): Record<string, { x: number; y: number }> {
  const copiedVals = Object.values(copied)
  const existingVals = Object.values(existing)
  if (copiedVals.length === 0 || existingVals.length === 0) return copied

  const existingMaxX = Math.max(...existingVals.map((p) => p.x))
  const existingMinY = Math.min(...existingVals.map((p) => p.y))
  const copiedMinX = Math.min(...copiedVals.map((p) => p.x))
  const copiedMinY = Math.min(...copiedVals.map((p) => p.y))
  const dx = existingMaxX + PLACEMENT_GAP - copiedMinX
  const dy = existingMinY - copiedMinY

  const placed: Record<string, { x: number; y: number }> = {}
  for (const [id, pos] of Object.entries(copied)) placed[id] = { x: pos.x + dx, y: pos.y + dy }
  return placed
}

export function useEmbedWorkflow() {
  const { batchAddActivitiesAndEdges } = useWorkflowStoreActions()

  const insertEmbeddedGraph = useCallback(
    (result: CopyWorkflowGraphResult) => {
      const { edges, nodePositions } = useWorkflowStore.getState()
      // Atomic: append copied activities and merge their edges in one transaction
      // (single undo entry via the store's temporal batch). batchAddActivitiesAndEdges
      // replaces the edges array, so we pass existing + new.
      batchAddActivitiesAndEdges({
        activities: result.activities,
        edges: [...edges, ...result.edges],
      })
      // Place the copied graph clear of existing nodes, folded into the same undo entry
      // (skipTracking avoids a second entry).
      const positions = placeClearOfExisting(result.positions, nodePositions)
      useWorkflowStore.getState().updateNodePositions(positions, { skipTracking: true })
    },
    [batchAddActivitiesAndEdges]
  )

  return { insertEmbeddedGraph }
}
