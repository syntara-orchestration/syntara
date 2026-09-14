import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import { usePositionEventHandlers } from './usePositionEventHandlers'

const mockUpdateNodePositions = vi.fn()
const mockFitView = vi.fn().mockResolvedValue(undefined)

let storeState: Record<string, unknown> = {}

vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({ fitView: mockFitView }),
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

function makeNode(id: string, position = { x: 0, y: 0 }): NodeType {
  return { id, type: 'task', position, data: {} } as unknown as NodeType
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
})
