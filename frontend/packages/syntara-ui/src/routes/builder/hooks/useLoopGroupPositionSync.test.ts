import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { useLoopGroupPositionSync } from './useLoopGroupPositionSync'

const mockUpdateNodeInternals = vi.fn()
const mockUpdateNodePositions = vi.fn()

let storeState: Record<string, unknown> = {}

vi.mock('@xyflow/react', () => ({
  useUpdateNodeInternals: () => mockUpdateNodeInternals,
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: Record<string, unknown>) => unknown) => selector(storeState),
  selectWorkflowVersion: (state: Record<string, unknown>) => state.workflowVersion,
  selectTriggers: (state: Record<string, unknown>) =>
    (state.currentWorkflow as { triggers?: Array<{ id: string }> } | undefined)?.triggers,
}))

function makeNode(id: string, type = 'task', position = { x: 0, y: 0 }): NodeType {
  return { id, type, position, data: {} } as unknown as NodeType
}

function makeEdge(id: string, source: string, target: string, sourceHandle: string): EdgeType {
  return { id, source, target, sourceHandle } as unknown as EdgeType
}

describe('useLoopGroupPositionSync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storeState = { workflowVersion: 1, currentWorkflow: { triggers: [] } }
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })

  it('does nothing before initialization', () => {
    renderHook(() =>
      useLoopGroupPositionSync({
        nodes: [makeNode('loop-1', 'loop')],
        edges: [],
        isInitialized: false,
        updateNodePositions: mockUpdateNodePositions,
      })
    )

    expect(mockUpdateNodePositions).not.toHaveBeenCalled()
    expect(mockUpdateNodeInternals).not.toHaveBeenCalled()
  })

  it('syncs loop group positions and refreshes node internals after init', () => {
    const nodes = [makeNode('loop-1', 'loop', { x: 10, y: 20 }), makeNode('task-1', 'task', { x: 110, y: 70 })]
    const edges = [makeEdge('e-loop', 'loop-1', 'task-1', 'loop')]

    renderHook(() =>
      useLoopGroupPositionSync({
        nodes,
        edges,
        isInitialized: true,
        updateNodePositions: mockUpdateNodePositions,
      })
    )

    expect(mockUpdateNodePositions).toHaveBeenCalledWith(
      {
        'loop-1': { x: 10, y: 20 },
        'task-1': { x: 110, y: 70 },
      },
      { skipTracking: true, markDirty: false }
    )
    expect(mockUpdateNodeInternals).toHaveBeenCalledWith('loop-1')
    expect(mockUpdateNodeInternals).toHaveBeenCalledWith('task-1')
  })

  it('runs only once per workflow version', () => {
    const nodes = [makeNode('loop-1', 'loop', { x: 10, y: 20 }), makeNode('task-1', 'task', { x: 110, y: 70 })]
    const edges = [makeEdge('e-loop', 'loop-1', 'task-1', 'loop')]

    const { rerender } = renderHook(
      ({ nodes: hookNodes }) =>
        useLoopGroupPositionSync({
          nodes: hookNodes,
          edges,
          isInitialized: true,
          updateNodePositions: mockUpdateNodePositions,
        }),
      { initialProps: { nodes } }
    )

    expect(mockUpdateNodePositions).toHaveBeenCalledTimes(1)

    rerender({ nodes })
    expect(mockUpdateNodePositions).toHaveBeenCalledTimes(1)

    storeState = { ...storeState, workflowVersion: 2 }
    rerender({ nodes })
    expect(mockUpdateNodePositions).toHaveBeenCalledTimes(2)
  })
})
