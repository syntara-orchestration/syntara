import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useBuilderFlowSideEffects } from './useBuilderFlowSideEffects'
import { useNodeDeletion } from './useNodeDeletion'
import { useNodePositioning } from './useNodePositioning'

const mockUseNodeDeletion = vi.mocked(useNodeDeletion)
const mockUseNodePositioning = vi.mocked(useNodePositioning)

vi.mock('./useNodeDeletion', () => ({ useNodeDeletion: vi.fn(() => ({ onNodesDelete: vi.fn() })) }))
vi.mock('./useNodePositioning', () => ({ useNodePositioning: vi.fn() }))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showError: vi.fn() }),
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStoreActions: () => ({
    updateNodePositions: vi.fn(),
  }),
}))

const baseParams = {
  graph: {
    nodes: [],
    edges: [],
    setNodes: vi.fn(),
    setEdges: vi.fn(),
    newlyAddedNodeIdsRef: { current: new Set<string>() },
    isDeletingRef: { current: false },
  },
  workflow: {
    storedEdges: [],
    isInitialized: true,
  },
  panel: {},
  callbacks: {},
  refs: {
    containerRef: { current: null },
    reactFlowInstance: {
      getViewport: vi.fn(),
      updateNode: vi.fn(),
    },
  },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useBuilderFlowSideEffects', () => {
  it('passes builder-owned node tracking into positioning', () => {
    const onNodesDelete = vi.fn()
    mockUseNodeDeletion.mockReturnValue({ onNodesDelete })

    const { result } = renderHook(() => useBuilderFlowSideEffects(baseParams))

    expect(mockUseNodePositioning).toHaveBeenCalledWith(
      expect.objectContaining({ newlyAddedNodeIdsRef: baseParams.graph.newlyAddedNodeIdsRef })
    )
    expect(mockUseNodeDeletion).toHaveBeenCalledWith(
      expect.objectContaining({
        nodes: [],
        edges: [],
        isDeletingRef: baseParams.graph.isDeletingRef,
      })
    )
    expect(result.current.onNodesDelete).toBe(onNodesDelete)
  })
})
