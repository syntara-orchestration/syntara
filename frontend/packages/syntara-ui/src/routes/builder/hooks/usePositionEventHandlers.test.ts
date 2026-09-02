import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { usePositionEventHandlers } from './usePositionEventHandlers'

const mockUpdateNodePositions = vi.fn()
const mockFitView = vi.fn().mockResolvedValue(undefined)
const mockGetNodes = vi.fn()

let storeState: Record<string, unknown> = {}

vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({ fitView: mockFitView, getNodes: mockGetNodes }),
}))

vi.mock('../../../stores/useWorkflowStore', () => {
  const useWorkflowStore = (selector: (state: Record<string, unknown>) => unknown) => selector(storeState)
  useWorkflowStore.getState = () => storeState

  return {
    useWorkflowStore,
    useWorkflowStoreActions: () => ({
      updateNodePositions: mockUpdateNodePositions,
    }),
    selectCurrentWorkflow: (state: Record<string, unknown>) => state.currentWorkflow,
    selectPositionUndoVersion: (state: Record<string, unknown>) => state._positionUndoVersion ?? 0,
  }
})

vi.mock('../utils/layoutEngine', () => ({
  getLayoutedElements: (nodes: NodeType[], edges: unknown[]) => ({
    nodes: nodes.map((n, i) => ({ ...n, position: { x: i * 100, y: 0 } })),
    edges,
  }),
}))

function makeNode(id: string, position = { x: 0, y: 0 }, type = 'task'): NodeType {
  return { id, type, position, data: {} } as unknown as NodeType
}

function makeEdge(id: string, source: string, target: string, sourceHandle: string): EdgeType {
  return { id, source, target, sourceHandle } as unknown as EdgeType
}

describe('usePositionEventHandlers', () => {
  const mockSetNodes = vi.fn()
  const mockSetEdges = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    storeState = {
      currentWorkflow: {
        triggers: [{ id: 'trigger_manual', type: 'manual_trigger', parameters: {} }],
      },
      _positionUndoVersion: 0,
      nodePositions: {},
    }
  })

  function renderSyncHook(nodes: NodeType[] = [], edges: unknown[] = []) {
    return renderHook(() => usePositionEventHandlers(nodes, edges as never[], mockSetNodes, mockSetEdges))
  }

  describe('onNodeDragStop', () => {
    it('maps trigger display IDs to definition IDs', () => {
      const { result } = renderSyncHook()
      const draggedNode = makeNode('trigger-0', { x: 50, y: 60 })

      result.current.onNodeDragStop({} as never, draggedNode, [draggedNode])

      expect(mockUpdateNodePositions).toHaveBeenCalledWith({ trigger_manual: { x: 50, y: 60 } })
    })

    it('passes through activity IDs unchanged', () => {
      const { result } = renderSyncHook()
      const draggedNode = makeNode('task-1', { x: 100, y: 200 })

      result.current.onNodeDragStop({} as never, draggedNode, [draggedNode])

      expect(mockUpdateNodePositions).toHaveBeenCalledWith({ 'task-1': { x: 100, y: 200 } })
    })

    it('does not call updateNodePositions for empty drag array', () => {
      const { result } = renderSyncHook()

      result.current.onNodeDragStop({} as never, makeNode('n'), [])

      expect(mockUpdateNodePositions).not.toHaveBeenCalled()
    })
  })

  describe('onLayout', () => {
    it('calls updateNodePositions with markDirty true when markDirty is true', () => {
      const nodes = [makeNode('task-1')]
      const { result } = renderSyncHook(nodes)

      result.current.onLayout({ markDirty: true })

      expect(mockUpdateNodePositions).toHaveBeenCalledWith(
        { 'task-1': { x: 0, y: 0 } },
        { skipTracking: false, markDirty: true }
      )
    })

    it('calls updateNodePositions with markDirty false when markDirty is false', () => {
      const nodes = [makeNode('task-1')]
      const { result } = renderSyncHook(nodes)

      result.current.onLayout({ markDirty: false })

      expect(mockUpdateNodePositions).toHaveBeenCalledWith(
        { 'task-1': { x: 0, y: 0 } },
        { skipTracking: true, markDirty: false }
      )
    })

    it('maps trigger node IDs to definition IDs in layout positions', () => {
      const nodes = [makeNode('trigger-0'), makeNode('task-1')]
      const { result } = renderSyncHook(nodes)

      result.current.onLayout()

      const positions = mockUpdateNodePositions.mock.calls[0][0] as Record<string, { x: number; y: number }>
      expect(positions).toHaveProperty('trigger_manual')
      expect(mockUpdateNodePositions).toHaveBeenCalledWith(positions, { skipTracking: true, markDirty: false })
    })

    it('calls fitView after layout', () => {
      const { result } = renderSyncHook([makeNode('task-1')])

      result.current.onLayout()

      expect(mockFitView).toHaveBeenCalledWith({ maxZoom: 1 })
    })
  })

  describe('loop group drag', () => {
    it('moves body nodes alongside the loop node during drag', () => {
      const loopNode = makeNode('loop-1', { x: 0, y: 0 }, 'loop')
      const bodyNode = makeNode('task-1', { x: 100, y: 50 }, 'task')
      const edges = [makeEdge('e-loop', 'loop-1', 'task-1', 'loop')]
      const { result } = renderSyncHook([loopNode, bodyNode], edges)

      result.current.onNodeDragStart({} as never, loopNode, [loopNode])
      const movedLoopNode = makeNode('loop-1', { x: 40, y: 20 }, 'loop')
      result.current.onNodeDrag({} as never, movedLoopNode)

      expect(mockSetNodes).toHaveBeenCalled()
      const updater = mockSetNodes.mock.calls[0][0] as (prev: NodeType[]) => NodeType[]
      const updated = updater([loopNode, bodyNode])
      const updatedBody = updated.find((n) => n.id === 'task-1')

      // Body should be at new loop position + original offset (100, 50)
      expect(updatedBody?.position).toEqual({ x: 140, y: 70 })
    })

    it('does not call setNodes when dragging a non-loop node', () => {
      const taskNode = makeNode('task-1', { x: 0, y: 0 }, 'task')
      const { result } = renderSyncHook([taskNode])

      result.current.onNodeDragStart({} as never, taskNode, [taskNode])
      result.current.onNodeDrag({} as never, makeNode('task-1', { x: 50, y: 30 }, 'task'))

      expect(mockSetNodes).not.toHaveBeenCalled()
    })

    it('does not start group drag when loop has no body nodes', () => {
      const loopNode = makeNode('loop-1', { x: 0, y: 0 }, 'loop')
      const { result } = renderSyncHook([loopNode], []) // no edges connecting body

      result.current.onNodeDragStart({} as never, loopNode, [loopNode])
      result.current.onNodeDrag({} as never, makeNode('loop-1', { x: 50, y: 30 }, 'loop'))

      expect(mockSetNodes).not.toHaveBeenCalled()
    })

    it('persists loop and body positions together in one updateNodePositions call', () => {
      const loopNode = makeNode('loop-1', { x: 0, y: 0 }, 'loop')
      const bodyNode = makeNode('task-1', { x: 100, y: 50 }, 'task')
      const edges = [makeEdge('e-loop', 'loop-1', 'task-1', 'loop')]
      const { result } = renderSyncHook([loopNode, bodyNode], edges)

      result.current.onNodeDragStart({} as never, loopNode, [loopNode])
      const movedLoopNode = makeNode('loop-1', { x: 40, y: 20 }, 'loop')
      result.current.onNodeDragStop({} as never, movedLoopNode, [movedLoopNode])

      expect(mockUpdateNodePositions).toHaveBeenCalledWith({
        'loop-1': { x: 40, y: 20 },
        'task-1': { x: 140, y: 70 },
      })
    })

    it('persists body positions from drag offsets when getNodes would be stale', () => {
      const loopNode = makeNode('loop-1', { x: 0, y: 0 }, 'loop')
      const bodyNode = makeNode('task-1', { x: 100, y: 50 }, 'task')
      const edges = [makeEdge('e-loop', 'loop-1', 'task-1', 'loop')]
      const { result } = renderSyncHook([loopNode, bodyNode], edges)

      result.current.onNodeDragStart({} as never, loopNode, [loopNode])
      const movedLoopNode = makeNode('loop-1', { x: 40, y: 20 }, 'loop')
      mockGetNodes.mockReturnValue([movedLoopNode, bodyNode])
      result.current.onNodeDragStop({} as never, movedLoopNode, [movedLoopNode])

      expect(mockUpdateNodePositions).toHaveBeenCalledWith({
        'loop-1': { x: 40, y: 20 },
        'task-1': { x: 140, y: 70 },
      })
    })

    it('does not include body nodes when loop has no drag state on stop', () => {
      const loopNode = makeNode('loop-1', { x: 0, y: 0 }, 'loop')
      const { result } = renderSyncHook([loopNode])

      // Stop without a prior start (simulates edge case / programmatic drag)
      const movedLoopNode = makeNode('loop-1', { x: 40, y: 20 }, 'loop')
      result.current.onNodeDragStop({} as never, movedLoopNode, [movedLoopNode])

      expect(mockUpdateNodePositions).toHaveBeenCalledWith({ 'loop-1': { x: 40, y: 20 } })
    })

    it('skips already-selected body nodes to avoid double-movement', () => {
      const loopNode = makeNode('loop-1', { x: 0, y: 0 }, 'loop')
      const bodyNode = makeNode('task-1', { x: 100, y: 50 }, 'task')
      const edges = [makeEdge('e-loop', 'loop-1', 'task-1', 'loop')]
      const { result } = renderSyncHook([loopNode, bodyNode], edges)

      // Both loop and body node are in draggedNodes (multi-select)
      result.current.onNodeDragStart({} as never, loopNode, [loopNode, bodyNode])
      result.current.onNodeDrag({} as never, makeNode('loop-1', { x: 40, y: 20 }, 'loop'))

      // setNodes should NOT be called since body is already being dragged by React Flow
      expect(mockSetNodes).not.toHaveBeenCalled()
    })

    it('moves done-branch nodes alongside the loop node during drag', () => {
      const loopNode = makeNode('loop-1', { x: 0, y: 0 }, 'loop')
      const loopBodyNode = makeNode('task-loop', { x: 100, y: 50 }, 'task')
      const doneNode = makeNode('task-done', { x: 100, y: -80 }, 'task')
      const edges = [
        makeEdge('e-loop', 'loop-1', 'task-loop', 'loop'),
        makeEdge('e-done', 'loop-1', 'task-done', 'done'),
      ]
      const { result } = renderSyncHook([loopNode, loopBodyNode, doneNode], edges)

      result.current.onNodeDragStart({} as never, loopNode, [loopNode])
      const movedLoopNode = makeNode('loop-1', { x: 40, y: 20 }, 'loop')
      result.current.onNodeDrag({} as never, movedLoopNode)

      expect(mockSetNodes).toHaveBeenCalled()
      const updater = mockSetNodes.mock.calls[0][0] as (prev: NodeType[]) => NodeType[]
      const updated = updater([loopNode, loopBodyNode, doneNode])
      const updatedDone = updated.find((n) => n.id === 'task-done')

      expect(updatedDone?.position).toEqual({ x: 140, y: -60 })
    })
  })
})
