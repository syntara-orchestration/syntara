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
/** Grid spacing (px) used to lay out copied nodes that carry no source coordinates. */
const GENERATED_COL_GAP = 220
const GENERATED_ROW_GAP = 160
const GENERATED_COLS = 4

/**
 * Compute canvas positions for the copied graph, placed clear of the existing nodes
 * (to the right, top-aligned) instead of a blind fixed offset that stacks the copy on
 * top of the current canvas.
 *
 * - Copied nodes that carry source coordinates keep their relative layout and are shifted
 *   as a block (D3: keep coordinates, move right of the farthest-right existing step).
 * - Copied nodes with NO source coordinates (e.g. a source saved without canvas positions)
 *   are given a generated grid position so they never collapse onto a single point (the
 *   stacking bug). They sit below any coordinate-bearing block.
 * - When there are no existing nodes and every copied node already has a coordinate, the
 *   source layout is kept verbatim (nothing to sit beside).
 */
function placeClearOfExisting(
  copiedIds: string[],
  copied: Record<string, { x: number; y: number }>,
  existing: Record<string, { x: number; y: number }>
): Record<string, { x: number; y: number }> {
  if (copiedIds.length === 0) return copied

  const existingVals = Object.values(existing)
  const known = copiedIds.filter((id) => copied[id])
  const missing = copiedIds.filter((id) => !copied[id])

  // Nothing to place beside, and every node already has a coordinate: keep as-is.
  if (existingVals.length === 0 && missing.length === 0) return copied

  const baseX = existingVals.length > 0 ? Math.max(...existingVals.map((p) => p.x)) + PLACEMENT_GAP : 0
  const baseY = existingVals.length > 0 ? Math.min(...existingVals.map((p) => p.y)) : 0

  const placed: Record<string, { x: number; y: number }> = {}

  // Coordinate-bearing nodes: preserve relative layout, shifted so the block's top-left
  // lands at the base point (only shifted when there are existing nodes to clear).
  if (known.length > 0) {
    const knownVals = known.map((id) => copied[id])
    const dx = existingVals.length > 0 ? baseX - Math.min(...knownVals.map((p) => p.x)) : 0
    const dy = existingVals.length > 0 ? baseY - Math.min(...knownVals.map((p) => p.y)) : 0
    for (const id of known) placed[id] = { x: copied[id].x + dx, y: copied[id].y + dy }
  }

  // Coordinate-less nodes: generated grid, below any preserved block.
  if (missing.length > 0) {
    const placedVals = Object.values(placed)
    const startY = placedVals.length > 0 ? Math.max(...placedVals.map((p) => p.y)) + GENERATED_ROW_GAP : baseY
    missing.forEach((id, i) => {
      placed[id] = {
        x: baseX + (i % GENERATED_COLS) * GENERATED_COL_GAP,
        y: startY + Math.floor(i / GENERATED_COLS) * GENERATED_ROW_GAP,
      }
    })
  }

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
      // Place every copied node clear of existing nodes (coordinate-less nodes get a
      // generated layout rather than stacking), folded into the same undo entry.
      const copiedIds = result.activities.map((a) => a.id)
      const positions = placeClearOfExisting(copiedIds, result.positions, nodePositions)
      useWorkflowStore.getState().updateNodePositions(positions, { skipTracking: true })
    },
    [batchAddActivitiesAndEdges]
  )

  return { insertEmbeddedGraph }
}
