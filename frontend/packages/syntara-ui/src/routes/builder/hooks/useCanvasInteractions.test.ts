import { act, renderHook } from '@testing-library/react'
import type { EdgeChange, NodeChange } from '@xyflow/react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { useCanvasInteractions } from './useCanvasInteractions'

vi.mock('../../../utils/detachPromise', () => ({
  detachPromise: (promise: Promise<unknown>) => promise,
}))

vi.mock('../utils/validateConnection', () => ({
  validateConnection: () => true,
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

  it('keeps render-only fields out of controlled state for replacement and add changes', () => {
    const currentNodes: NodeType[] = [
      {
        ...nodes[0],
        type: FlowNodeType.TASK,
        data: { name: 'Task', metadata: { label: 'task' } },
      } as unknown as NodeType,
    ]
    let updatedNodes = currentNodes
    let updatedEdges: EdgeType[] = edges.map((edge) => ({ ...edge, data: {} }))
    const setNodes = vi.fn((updater: NodeType[] | ((current: NodeType[]) => NodeType[])) => {
      updatedNodes = typeof updater === 'function' ? updater(updatedNodes) : updater
    })
    const setEdges = vi.fn((updater: EdgeType[] | ((current: EdgeType[]) => EdgeType[])) => {
      updatedEdges = typeof updater === 'function' ? updater(updatedEdges) : updater
    })
    const { result } = renderHook(() =>
      useCanvasInteractions({
        isReadOnly: false,
        edges: updatedEdges,
        nodes: updatedNodes,
        fitView: vi.fn().mockResolvedValue(true),
        isInitialized: true,
        setNodes,
        setEdges,
      })
    )

    const projectedNode = {
      ...currentNodes[0],
      type: FlowNodeType.TASK_REVERSED,
      selected: true,
      className: 'custom has-button-edge handle-source-connected',
      data: {
        ...currentNodes[0].data,
        __executionState: { status: 'running' },
        __validationError: true,
        metadata: {
          label: 'task',
          __mockDataPinned: true,
          __reverseHandles: true,
          __showExecutionBadge: true,
        },
      },
    } as NodeType
    const addedNode = { ...projectedNode, id: 'task-2' }
    act(() => {
      result.current.onNodesChange([
        { type: 'replace', id: 'task-1', item: projectedNode },
        { type: 'add', item: addedNode, index: 1 },
      ] as NodeChange<NodeType>[])
    })

    expect(updatedNodes[0].type).toBe(FlowNodeType.TASK)
    expect(updatedNodes[0].selected).toBe(false)
    expect(updatedNodes[0].className).toBe('custom')
    expect(updatedNodes[0].data).toEqual({ name: 'Task', metadata: { label: 'task' } })
    expect(updatedNodes[1].type).toBe(FlowNodeType.TASK)
    expect(updatedNodes[1].data).toEqual({ name: 'Task', metadata: { label: 'task' } })

    const onAddNode = vi.fn()
    const projectedEdge = {
      ...updatedEdges[0],
      markerEnd: { type: 'arrowclosed', width: 12, height: 12, color: 'black' },
      data: { isActive: true, executionStatus: 'passed', onAddNode },
    } as unknown as EdgeType
    const addedEdge = { ...projectedEdge, id: 'e2' }
    act(() => {
      result.current.onEdgesChange([
        { type: 'replace', id: 'e1', item: projectedEdge },
        { type: 'add', item: addedEdge, index: 1 },
      ] as EdgeChange<EdgeType>[])
    })

    expect(updatedEdges[0].data).toEqual({})
    expect(updatedEdges[0].markerEnd).toBeUndefined()
    expect(updatedEdges[1].data).toBeUndefined()
    expect(updatedEdges[1].markerEnd).toBeUndefined()
  })

  it('ignores React Flow changes for projected placeholders, button edges, and pending edges', () => {
    let currentNodes = [...nodes]
    let currentEdges = [...edges]
    const setNodes = vi.fn((updater: NodeType[] | ((current: NodeType[]) => NodeType[])) => {
      currentNodes = typeof updater === 'function' ? updater(currentNodes) : updater
    })
    const setEdges = vi.fn((updater: EdgeType[] | ((current: EdgeType[]) => EdgeType[])) => {
      currentEdges = typeof updater === 'function' ? updater(currentEdges) : updater
    })
    const { result } = renderHook(() =>
      useCanvasInteractions({
        isReadOnly: false,
        edges: currentEdges,
        nodes: currentNodes,
        fitView: vi.fn().mockResolvedValue(true),
        isInitialized: true,
        setNodes,
        setEdges,
      })
    )

    const placeholder = {
      id: 'placeholder-task-1',
      type: FlowNodeType.PLACEHOLDER,
      position: { x: 0, y: 0 },
      data: {},
    } as unknown as NodeType
    const buttonEdge = { id: 'button-task-1', source: 'task-1', target: placeholder.id, type: 'buttonEdge' } as EdgeType
    const pendingEdge = { id: 'pending-task-1', source: 'task-1', target: 'pending-target-task-1' } as EdgeType

    act(() => {
      result.current.onNodesChange([
        { type: 'add', item: placeholder, index: 1 },
        { type: 'remove', id: 'pending-target-task-1' },
      ] as NodeChange<NodeType>[])
      result.current.onEdgesChange([
        { type: 'add', item: buttonEdge, index: 1 },
        { type: 'remove', id: pendingEdge.id },
      ] as EdgeChange<EdgeType>[])
    })

    expect(currentNodes).toEqual(nodes)
    expect(currentEdges).toEqual(edges)
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
