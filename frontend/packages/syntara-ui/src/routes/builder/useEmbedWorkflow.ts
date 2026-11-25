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

import type { EdgeConnection } from './types/edge'
import type { CopyWorkflowGraphResult } from './utils/embed/copyWorkflowGraph'

/** Card width (px) for the pre-render layout math; mirrors the builder's default node width. */
const NODE_WIDTH = 300
/** Horizontal gap between consecutive ranks; mirrors the dagre engine's ranksep. */
const RANK_GAP = 120
/**
 * Vertical pitch between stacked same-rank siblings. Card height varies and is unmeasured
 * pre-render, so this assumes an expanded card (header + parameters) plus a gap, erring
 * toward separation rather than overlap; the canvas "Reset layout" later tightens the
 * spacing using the real measured heights.
 */
const SIBLING_PITCH = 340
/** Gap between the farthest-right existing node and the embedded block. */
const PLACEMENT_GAP = 120

/**
 * Rank each copied node by its longest path from a root, so a copied pipeline reads left to
 * right as a pipeline. Self-loops are ignored, and any node left unranked by a cycle (or with
 * no internal edges) falls back to rank 0 rather than being dropped.
 */
function rankCopiedNodes(copiedIds: string[], edges: EdgeConnection[]): Map<string, number> {
  const ids = new Set(copiedIds)
  const children = new Map<string, string[]>()
  const indegree = new Map<string, number>()
  for (const id of copiedIds) {
    children.set(id, [])
    indegree.set(id, 0)
  }
  for (const e of edges) {
    // Internal edges only; skip self-loops so a node never blocks its own ranking.
    if (!ids.has(e.source) || !ids.has(e.target) || e.source === e.target) continue
    children.get(e.source)?.push(e.target)
    indegree.set(e.target, (indegree.get(e.target) ?? 0) + 1)
  }

  const rank = new Map<string, number>(copiedIds.map((id) => [id, 0]))
  const remaining = new Map(indegree)
  // Kahn's algorithm relaxing to the longest path; nodes stuck in a cycle keep rank 0.
  const queue = copiedIds.filter((id) => (remaining.get(id) ?? 0) === 0)
  while (queue.length > 0) {
    const id = queue.shift() as string
    for (const child of children.get(id) ?? []) {
      rank.set(child, Math.max(rank.get(child) ?? 0, (rank.get(id) ?? 0) + 1))
      const left = (remaining.get(child) ?? 0) - 1
      remaining.set(child, left)
      if (left === 0) queue.push(child)
    }
  }
  return rank
}

/**
 * Lay the copied block out fresh as a left-to-right flow, placed clear of the existing nodes
 * (to the right, top-aligned). Source coordinates are intentionally ignored: a source saved
 * with collapsed or overlapping cards would otherwise reproduce that overlap in the copy. The
 * layout is deterministic and needs no measured widths, so it runs synchronously inside the
 * insert (one undo entry); the canvas "Reset layout" still applies the full dagre layout.
 */
function autoLayoutClearOfExisting(
  copiedIds: string[],
  edges: EdgeConnection[],
  existing: Record<string, { x: number; y: number }>
): Record<string, { x: number; y: number }> {
  if (copiedIds.length === 0) return {}

  const rank = rankCopiedNodes(copiedIds, edges)
  const rowInRank = new Map<number, number>()
  const existingVals = Object.values(existing)
  // Clear the full width of the farthest-right existing node, not just its origin point.
  const baseX = existingVals.length > 0 ? Math.max(...existingVals.map((p) => p.x)) + NODE_WIDTH + PLACEMENT_GAP : 0
  const baseY = existingVals.length > 0 ? Math.min(...existingVals.map((p) => p.y)) : 0

  const placed: Record<string, { x: number; y: number }> = {}
  for (const id of copiedIds) {
    const r = rank.get(id) ?? 0
    const row = rowInRank.get(r) ?? 0
    rowInRank.set(r, row + 1)
    placed[id] = {
      x: baseX + r * (NODE_WIDTH + RANK_GAP),
      y: baseY + row * SIBLING_PITCH,
    }
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
      // Lay the copied block out fresh and place it clear of existing nodes, folded into the
      // same undo entry so insert + placement are one undoable step.
      const copiedIds = result.activities.map((a) => a.id)
      const positions = autoLayoutClearOfExisting(copiedIds, result.edges, nodePositions)
      useWorkflowStore.getState().updateNodePositions(positions, { skipTracking: true })
    },
    [batchAddActivitiesAndEdges]
  )

  return { insertEmbeddedGraph }
}
