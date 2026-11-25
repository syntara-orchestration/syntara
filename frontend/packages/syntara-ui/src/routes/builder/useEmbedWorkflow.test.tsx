import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useEmbedWorkflow } from './useEmbedWorkflow'
import type { CopyWorkflowGraphResult } from './utils/embed/copyWorkflowGraph'

const batchAddActivitiesAndEdges = vi.fn()
const updateNodePositions = vi.fn()
let storeState: {
  edges: unknown[]
  nodePositions: Record<string, { x: number; y: number }>
  updateNodePositions: typeof updateNodePositions
}

vi.mock('../../stores/useWorkflowStore', () => ({ useWorkflowStore: { getState: () => storeState } }))
vi.mock('../../stores/workflowStoreSelectors', () => ({
  useWorkflowStoreActions: () => ({ batchAddActivitiesAndEdges }),
}))

const makeResult = (
  activityIds: string[],
  edges: Array<{ id: string; source: string; target: string }> = []
): CopyWorkflowGraphResult =>
  ({
    activities: activityIds.map((id) => ({ id })),
    edges,
    positions: {},
    idMap: new Map(),
    droppedEdgeCount: 0,
    resourceReferenceNodes: [],
    subWorkflowNodes: [],
    danglingExpressionRefs: [],
  }) as unknown as CopyWorkflowGraphResult

describe('useEmbedWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storeState = { edges: [{ id: 'e0' }], nodePositions: {}, updateNodePositions }
  })

  it('lays the copied graph out as a left-to-right flow, clear of existing nodes', () => {
    storeState.nodePositions = { a: { x: 0, y: 0 }, b: { x: 100, y: 50 } }
    const { result } = renderHook(() => useEmbedWorkflow())
    result.current.insertEmbeddedGraph(makeResult(['c1', 'c2'], [{ id: 'e1', source: 'c1', target: 'c2' }]))

    // baseX = existingMaxX(100) + NODE_WIDTH(300) + GAP(120) = 520 ; baseY = existingMinY(0).
    // c1 is rank 0, c2 rank 1 => c2.x = 520 + (NODE_WIDTH 300 + RANK_GAP 120) = 940, same row.
    expect(updateNodePositions).toHaveBeenCalledWith(
      { c1: { x: 520, y: 0 }, c2: { x: 940, y: 0 } },
      { skipTracking: true }
    )
    expect(batchAddActivitiesAndEdges).toHaveBeenCalledWith({
      activities: [{ id: 'c1' }, { id: 'c2' }],
      edges: [{ id: 'e0' }, { id: 'e1', source: 'c1', target: 'c2' }],
    })
  })

  it('lays out from the origin when the canvas has no existing nodes', () => {
    storeState.nodePositions = {}
    const { result } = renderHook(() => useEmbedWorkflow())
    result.current.insertEmbeddedGraph(makeResult(['c1']))
    expect(updateNodePositions).toHaveBeenCalledWith({ c1: { x: 0, y: 0 } }, { skipTracking: true })
  })

  it('stacks sibling (same-rank) copied nodes without overlap, clear of existing nodes', () => {
    storeState.nodePositions = { a: { x: 0, y: 0 }, b: { x: 200, y: 0 } }
    const { result } = renderHook(() => useEmbedWorkflow())
    // Three nodes with no internal edges => all rank 0, stacked vertically.
    result.current.insertEmbeddedGraph(makeResult(['n1', 'n2', 'n3']))

    const placed = updateNodePositions.mock.calls[0][0] as Record<string, { x: number; y: number }>
    expect(Object.keys(placed).sort()).toEqual(['n1', 'n2', 'n3'])
    const pts = Object.values(placed)
    // Distinct points (no stacking bug), all sharing the first rank's x clear of existing width.
    expect(new Set(pts.map((p) => `${p.x},${p.y}`)).size).toBe(3)
    expect(pts.every((p) => p.x === 200 + 300 + 120)).toBe(true)
    // Vertical pitch must clear an expanded card (header + parameters) so stacked
    // siblings never overlap; guards against regressing to the collapsed-height pitch.
    const ys = pts.map((p) => p.y).sort((m, n) => m - n)
    expect(ys[1] - ys[0]).toBeGreaterThanOrEqual(300)
    expect(ys[2] - ys[1]).toBeGreaterThanOrEqual(300)
  })
})
