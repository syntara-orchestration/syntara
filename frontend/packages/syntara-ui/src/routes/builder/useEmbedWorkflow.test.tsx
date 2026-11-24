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
  positions: Record<string, { x: number; y: number }>,
  activityIds: string[] = Object.keys(positions)
): CopyWorkflowGraphResult =>
  ({
    activities: activityIds.map((id) => ({ id })),
    edges: [{ id: 'ce', source: 'c1', target: 'c1' }],
    positions,
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

  it('places the copied graph clear of existing nodes (to the right with a gap)', () => {
    storeState.nodePositions = { a: { x: 0, y: 0 }, b: { x: 100, y: 50 } }
    const { result } = renderHook(() => useEmbedWorkflow())
    result.current.insertEmbeddedGraph(makeResult({ c1: { x: 0, y: 0 }, c2: { x: 50, y: 20 } }))

    // existingMaxX=100, GAP=120, copiedMinX=0 => dx=220 ; existingMinY=0, copiedMinY=0 => dy=0
    expect(updateNodePositions).toHaveBeenCalledWith(
      { c1: { x: 220, y: 0 }, c2: { x: 270, y: 20 } },
      { skipTracking: true }
    )
    expect(batchAddActivitiesAndEdges).toHaveBeenCalledWith({
      activities: [{ id: 'c1' }, { id: 'c2' }],
      edges: [{ id: 'e0' }, { id: 'ce', source: 'c1', target: 'c1' }],
    })
  })

  it('leaves positions unchanged when the canvas has no existing nodes', () => {
    storeState.nodePositions = {}
    const { result } = renderHook(() => useEmbedWorkflow())
    const positions = { c1: { x: 5, y: 7 } }
    result.current.insertEmbeddedGraph(makeResult(positions))
    expect(updateNodePositions).toHaveBeenCalledWith(positions, { skipTracking: true })
  })

  it('generates a non-overlapping grid for copied nodes that have no source coordinates', () => {
    storeState.nodePositions = { a: { x: 0, y: 0 }, b: { x: 200, y: 0 } }
    const { result } = renderHook(() => useEmbedWorkflow())
    // No positions for the three copied nodes (source saved without canvas coordinates).
    result.current.insertEmbeddedGraph(makeResult({}, ['n1', 'n2', 'n3']))

    const placed = updateNodePositions.mock.calls[0][0] as Record<string, { x: number; y: number }>
    expect(Object.keys(placed).sort()).toEqual(['n1', 'n2', 'n3'])
    // Every node gets a distinct point (no stacking) and all sit right of the existing nodes.
    const pts = Object.values(placed)
    const unique = new Set(pts.map((p) => `${p.x},${p.y}`))
    expect(unique.size).toBe(3)
    expect(pts.every((p) => p.x >= 200)).toBe(true)
  })
})
