import { act, renderHook } from '@testing-library/react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { useCanvasInteractions } from './useCanvasInteractions'

vi.mock('../../../utils/detachPromise', () => ({
  detachPromise: (promise: Promise<unknown>) => promise,
}))

vi.mock('../utils/validateConnection', () => ({
  validateConnection: () => true,
}))

vi.mock('./useExternalNodeSelection', () => ({
  useExternalNodeSelection: vi.fn(),
}))

const nodes = [{ id: 'task-1', position: { x: 0, y: 0 }, data: {}, selected: false }] as NodeType[]
const edges = [{ id: 'e1', source: 'trigger-0', target: 'task-1' }] as EdgeType[]

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useCanvasInteractions', () => {
  it('returns isValidConnection that delegates to validateConnection', () => {
    const setNodes = vi.fn()
    const setEdges = vi.fn()
    const { result } = renderHook(() =>
      useCanvasInteractions({
        isReadOnly: false,
        edges,
        nodes,
        fitView: vi.fn().mockResolvedValue(true),
        isInitialized: true,
        setNodes,
        setEdges,
      })
    )

    expect(result.current.isValidConnection({} as EdgeType)).toBe(true)
  })

  it('ignores destructive node changes in read-only mode', () => {
    let currentNodes = [...nodes]
    const setNodes = vi.fn((updater: NodeType[] | ((current: NodeType[]) => NodeType[])) => {
      currentNodes = typeof updater === 'function' ? updater(currentNodes) : updater
    })
    const setEdges = vi.fn()
    const { result } = renderHook(() =>
      useCanvasInteractions({
        isReadOnly: true,
        edges,
        nodes: currentNodes,
        fitView: vi.fn().mockResolvedValue(true),
        isInitialized: true,
        setNodes,
        setEdges,
      })
    )

    result.current.onNodesChange([{ type: 'remove', id: 'task-1' }])
    expect(currentNodes).toHaveLength(1)
    expect(currentNodes[0].id).toBe('task-1')
  })

  it('clears pending edge when panel closes', () => {
    const setNodes = vi.fn()
    const setEdges = vi.fn()
    const { result, rerender } = renderHook(
      ({ panelOpen }: { panelOpen: boolean }) =>
        useCanvasInteractions({
          isReadOnly: false,
          edges,
          nodes,
          panelOpen,
          fitView: vi.fn().mockResolvedValue(true),
          isInitialized: true,
          setNodes,
          setEdges,
        }),
      { initialProps: { panelOpen: true } }
    )

    act(() => {
      result.current.setPendingEdge({ sourceNodeId: 'task-1', x: 10, y: 20 })
    })
    expect(result.current.pendingEdge).not.toBeNull()

    rerender({ panelOpen: false })
    expect(result.current.pendingEdge).toBeNull()
  })

  it('calls fitView when panelOpen changes and canvas is initialized', () => {
    const fitView = vi.fn().mockResolvedValue(true)
    const setNodes = vi.fn()
    const setEdges = vi.fn()

    const { rerender } = renderHook(
      ({ panelOpen }: { panelOpen: boolean }) =>
        useCanvasInteractions({
          isReadOnly: false,
          edges,
          nodes,
          panelOpen,
          fitView,
          isInitialized: true,
          setNodes,
          setEdges,
        }),
      { initialProps: { panelOpen: false } }
    )

    rerender({ panelOpen: true })
    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(fitView).toHaveBeenCalledWith({ duration: 300, padding: 0.1 })
  })

  it('clears pending edge when the source node is removed', () => {
    const setNodes = vi.fn()
    const setEdges = vi.fn()
    const { result, rerender } = renderHook(
      ({ nodes: currentNodes }: { nodes: NodeType[] }) =>
        useCanvasInteractions({
          isReadOnly: false,
          edges,
          nodes: currentNodes,
          panelOpen: true,
          fitView: vi.fn().mockResolvedValue(true),
          isInitialized: true,
          setNodes,
          setEdges,
        }),
      { initialProps: { nodes } }
    )

    act(() => {
      result.current.setPendingEdge({ sourceNodeId: 'task-1', x: 10, y: 20 })
    })
    expect(result.current.pendingEdge).not.toBeNull()

    rerender({ nodes: [] })
    expect(result.current.pendingEdge).toBeNull()
  })
})
