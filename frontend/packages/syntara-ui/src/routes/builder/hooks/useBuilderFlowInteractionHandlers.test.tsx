import { act, renderHook } from '@testing-library/react'
import type { Edge, Node, ReactFlowInstance } from '@xyflow/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useBuilderFlowInteractionHandlers } from './useBuilderFlowInteractionHandlers'

const moveActivityBefore = vi.fn()

vi.mock('../../../stores/useWorkflowStore', () => ({
  getActivityMetadata: vi.fn((data: { __isGeneric?: boolean } | undefined) => data),
  useWorkflowStore: {
    getState: vi.fn(() => ({ moveActivityBefore })),
  },
}))

const calculateEdgeConnection = vi.hoisted(() => vi.fn(() => ({ activityReorderTarget: null as string | null })))
const applyEdgeConnection = vi.hoisted(() =>
  vi.fn((_r: unknown, _p: unknown, _t: unknown, _rf: unknown, onComplete?: () => void) => {
    onComplete?.()
  })
)

vi.mock('../utils/edgeConnectionHelpers', () => ({
  calculateEdgeConnection,
  applyEdgeConnection,
}))

function rf(partial: Partial<ReactFlowInstance>): ReactFlowInstance {
  return {
    getEdge: vi.fn(),
    getNode: vi.fn(),
    getNodes: vi.fn(() => []),
    ...partial,
  } as unknown as ReactFlowInstance
}

describe('useBuilderFlowInteractionHandlers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    calculateEdgeConnection.mockReturnValue({ activityReorderTarget: null })
  })

  function renderWith(dispatch = vi.fn()) {
    const duplicateActivity = vi.fn()
    const reactFlowInstance = rf({
      getEdge: vi.fn((): Edge | undefined => ({
        id: 'e0',
        source: 's',
        target: 't',
        targetHandle: 'loop',
      })),
      getNode: vi.fn(),
      getNodes: vi.fn(() => []),
    })
    const view = renderHook(() =>
      useBuilderFlowInteractionHandlers({
        reactFlowInstance,
        dispatch,
        duplicateActivity,
        edgeIdToReplace: 'e1',
        targetNodeId: 't1',
        sourceHandle: null,
        targetHandle: 'th',
        onRunStep: vi.fn(),
      })
    )
    return { ...view, dispatch, duplicateActivity, reactFlowInstance }
  }

  it('handleNodeClick dispatches NODE_CLICK with isGeneric from metadata', () => {
    const { result, dispatch } = renderWith()
    const node = {
      id: 'n1',
      position: { x: 0, y: 0 },
      data: { __isGeneric: true },
    } as unknown as Node
    act(() => {
      result.current.handleNodeClick({} as React.MouseEvent, node)
    })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'NODE_CLICK',
      payload: { node, isGeneric: true },
    })
  })

  it('handleClearDesiredPosition dispatches CLEAR_NEW_NODE_DESIRED_POSITION', () => {
    const { result, dispatch } = renderWith()
    act(() => {
      result.current.handleClearDesiredPosition()
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'CLEAR_NEW_NODE_DESIRED_POSITION' })
  })

  it('handleAddNodeFromEdge reads target handle from edge when edgeId is set', () => {
    const { result, dispatch, reactFlowInstance } = renderWith()
    vi.mocked(reactFlowInstance.getEdge).mockReturnValue({
      id: 'e1',
      source: 's',
      target: 't',
      targetHandle: 'custom',
    })
    act(() => {
      result.current.handleAddNodeFromEdge('s', 't', 'edge-1')
    })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'OPEN_ADD_NODE_FROM_EDGE',
      payload: {
        sourceId: 's',
        targetId: 't',
        edgeId: 'edge-1',
        handle: undefined,
        targetHandle: 'custom',
        desiredPosition: undefined,
      },
    })
  })

  it('handleAddNodeFromEdge leaves targetHandle undefined when edgeId is omitted', () => {
    const { result, dispatch } = renderWith()
    act(() => {
      result.current.handleAddNodeFromEdge('s', 't')
    })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'OPEN_ADD_NODE_FROM_EDGE',
      payload: {
        sourceId: 's',
        targetId: 't',
        edgeId: undefined,
        handle: undefined,
        targetHandle: undefined,
        desiredPosition: undefined,
      },
    })
  })

  it('handleAddNodeFromEdge uses undefined targetHandle when getEdge returns no edge', () => {
    const { result, dispatch, reactFlowInstance } = renderWith()
    vi.mocked(reactFlowInstance.getEdge).mockReturnValue(undefined)
    act(() => {
      result.current.handleAddNodeFromEdge('s', 't', 'edge-missing')
    })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'OPEN_ADD_NODE_FROM_EDGE',
      payload: {
        sourceId: 's',
        targetId: 't',
        edgeId: 'edge-missing',
        handle: undefined,
        targetHandle: undefined,
        desiredPosition: undefined,
      },
    })
  })

  it('handleConnectFromPanel calls moveActivityBefore when result has activityReorderTarget', () => {
    calculateEdgeConnection.mockReturnValue({ activityReorderTarget: 'before-id' })
    const { result } = renderWith()
    act(() => {
      result.current.handleConnectFromPanel('src', 'tgt')
    })
    expect(moveActivityBefore).toHaveBeenCalledWith('tgt', 'before-id')
  })

  it('handleConnectFromPanel does not reorder when activityReorderTarget is null', () => {
    moveActivityBefore.mockClear()
    calculateEdgeConnection.mockReturnValue({ activityReorderTarget: null })
    const { result } = renderWith()
    act(() => {
      result.current.handleConnectFromPanel('src', 'tgt')
    })
    expect(moveActivityBefore).not.toHaveBeenCalled()
  })

  it('handleNodesDeleted dispatches CLEAR_SELECTED_IF_DELETED', () => {
    const { result, dispatch } = renderWith()
    act(() => {
      result.current.handleNodesDeleted(['a', 'b'])
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'CLEAR_SELECTED_IF_DELETED', payload: ['a', 'b'] })
  })

  it('handleViewNodeDetails does nothing when node is missing', () => {
    const { result, dispatch, reactFlowInstance } = renderWith()
    vi.mocked(reactFlowInstance.getNode).mockReturnValue(undefined)
    act(() => {
      result.current.nodeActionsValue.onViewDetails('missing')
    })
    expect(dispatch).not.toHaveBeenCalled()
  })

  it('handleViewNodeDetails dispatches when node exists', () => {
    const { result, dispatch, reactFlowInstance } = renderWith()
    const node = { id: 'n1', position: { x: 0, y: 0 }, data: {} } as unknown as Node
    vi.mocked(reactFlowInstance.getNode).mockReturnValue(node)
    act(() => {
      result.current.nodeActionsValue.onViewDetails('n1')
    })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'NODE_CLICK',
      payload: { node, isGeneric: false },
    })
  })

  it('handleReplaceNode opens add panel with replacement id', () => {
    const { result, dispatch } = renderWith()
    act(() => {
      result.current.nodeActionsValue.onReplace('rep-1')
    })
    expect(dispatch).toHaveBeenCalledWith({
      type: 'OPEN_ADD_NODE_PANEL',
      payload: { sourceNodeId: null, replacementNodeId: 'rep-1' },
    })
  })

  it('handleDuplicateNode closes editor, sets desired position when node exists, and duplicates', () => {
    const { result, dispatch, duplicateActivity, reactFlowInstance } = renderWith()
    const dupNode = {
      id: 'dup',
      position: { x: 0, y: 0 },
      measured: { width: 300, height: 40 },
      data: {},
    } as unknown as Node
    vi.mocked(reactFlowInstance.getNode).mockReturnValue(dupNode)
    vi.mocked(reactFlowInstance.getNodes).mockReturnValue([dupNode])
    act(() => {
      result.current.nodeActionsValue.onDuplicate('dup')
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'CLOSE_NODE_EDITOR' })
    // y: vertical center of the duplicated node — node.position.y (0) + measured.height (40) / 2 = 20 (matches findDuplicatePosition centering)
    expect(dispatch).toHaveBeenCalledWith({
      type: 'SET_NEW_NODE_DESIRED_POSITION',
      payload: { x: 420, y: 20 },
    })
    expect(duplicateActivity).toHaveBeenCalledWith('dup')
  })

  it('handleDuplicateNode still calls duplicateActivity when getNode returns undefined', () => {
    const { result, duplicateActivity, reactFlowInstance } = renderWith()
    vi.mocked(reactFlowInstance.getNode).mockReturnValue(undefined)
    act(() => {
      result.current.nodeActionsValue.onDuplicate('id-only')
    })
    expect(duplicateActivity).toHaveBeenCalledWith('id-only')
  })
})
