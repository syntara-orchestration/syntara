import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { useLoopGroupPositionSync } from './useLoopGroupPositionSync'

const mockUpdateNodeInternals = vi.fn()
const mockUpdateNodePositions = vi.fn()

vi.mock('@xyflow/react', () => ({
  useUpdateNodeInternals: () => mockUpdateNodeInternals,
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
        workflowVersion: 1,
        triggers: [],
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
        workflowVersion: 1,
        triggers: [],
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
      ({ workflowVersion }) =>
        useLoopGroupPositionSync({
          nodes,
          edges,
          isInitialized: true,
          workflowVersion,
          triggers: [],
          updateNodePositions: mockUpdateNodePositions,
        }),
      { initialProps: { workflowVersion: 1 } }
    )

    expect(mockUpdateNodePositions).toHaveBeenCalledTimes(1)

    rerender({ workflowVersion: 1 })
    expect(mockUpdateNodePositions).toHaveBeenCalledTimes(1)

    rerender({ workflowVersion: 2 })
    expect(mockUpdateNodePositions).toHaveBeenCalledTimes(2)
  })
})
