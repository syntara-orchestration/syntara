import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityState } from '../../workflows/execution/types'

import { useBuilderFlowSideEffects } from './useBuilderFlowSideEffects'
import { useButtonEdgeMaintenance } from './useButtonEdgeMaintenance'
import { useEdgeExecutionStatus } from './useEdgeExecutionStatus'
import { useExecutionStateEnrichment } from './useExecutionStateEnrichment'
import { useNodeDeletion } from './useNodeDeletion'
import { useNodeUpdates } from './useNodeUpdates'

const mockUseNodeUpdates = vi.mocked(useNodeUpdates)
const mockUseNodeDeletion = vi.mocked(useNodeDeletion)
const mockUseExecutionStateEnrichment = vi.mocked(useExecutionStateEnrichment)
const mockUseEdgeExecutionStatus = vi.mocked(useEdgeExecutionStatus)
const mockUseButtonEdgeMaintenance = vi.mocked(useButtonEdgeMaintenance)

vi.mock('./useNodeUpdates', () => ({
  useNodeUpdates: vi.fn(() => ({ newlyAddedNodeIdsRef: { current: new Set() } })),
}))
vi.mock('./useEdgeSynchronization', () => ({ useEdgeSynchronization: vi.fn() }))
vi.mock('./useLoopBackNodeTypes', () => ({ useLoopBackNodeTypes: vi.fn() }))
vi.mock('./useLoopGroupPositionSync', () => ({ useLoopGroupPositionSync: vi.fn() }))
vi.mock('./useNodeDeletion', () => ({ useNodeDeletion: vi.fn(() => ({ onNodesDelete: vi.fn() })) }))
vi.mock('./useNodePositioning', () => ({ useNodePositioning: vi.fn() }))
vi.mock('./useButtonEdgeMaintenance', () => ({ useButtonEdgeMaintenance: vi.fn() }))
vi.mock('./useEdgeActiveState', () => ({ useEdgeActiveState: vi.fn() }))
vi.mock('./usePendingEdgeManagement', () => ({ usePendingEdgeManagement: vi.fn() }))
vi.mock('./useExecutionStateEnrichment', () => ({ useExecutionStateEnrichment: vi.fn() }))
vi.mock('./useValidationEnrichment', () => ({ useValidationEnrichment: vi.fn() }))
vi.mock('./useEdgeExecutionStatus', () => ({ useEdgeExecutionStatus: vi.fn() }))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showError: vi.fn() }),
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStoreActions: () => ({
    setEdges: vi.fn(),
    updateNodePositions: vi.fn(),
  }),
}))

const baseParams = {
  graph: {
    nodes: [],
    edges: [],
    initialNodes: [],
    initialEdges: [],
    setNodes: vi.fn(),
    setEdges: vi.fn(),
    isDeletingRef: { current: false },
  },
  workflow: {
    workflowVersion: 1,
    currentWorkflow: null,
    storedEdges: [],
    isInitialized: true,
    isReadOnly: false,
  },
  execution: {
    isActiveExecution: false,
    isExecutionView: false,
    effectiveExecutionStatus: null,
    activityStates: new Map(),
    preResolvedNodes: new Set<string>(),
    buttonEdgeExecutionStatus: null,
  },
  panel: {
    pendingEdge: null,
  },
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
  it('wires graph state into node update and deletion hooks', () => {
    const onNodesDelete = vi.fn()
    mockUseNodeDeletion.mockReturnValue({ onNodesDelete })

    const { result } = renderHook(() => useBuilderFlowSideEffects(baseParams))

    expect(mockUseNodeUpdates).toHaveBeenCalledWith(
      expect.objectContaining({
        initialNodes: [],
        initialEdges: [],
        isInitialized: true,
        workflowVersion: 1,
      })
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

  it('passes execution and panel state to enrichment hooks', () => {
    renderHook(() =>
      useBuilderFlowSideEffects({
        ...baseParams,
        execution: {
          ...baseParams.execution,
          effectiveExecutionStatus: 'running',
          activityStates: new Map<string, ActivityState>([['task-1', { activityId: 'task-1', status: 'running' }]]),
          preResolvedNodes: new Set(['task-1']),
        },
        panel: {
          pendingEdge: { sourceNodeId: 'task-1', x: 0, y: 0 },
          activeEdgeId: 'edge-1',
        },
      })
    )

    expect(mockUseExecutionStateEnrichment).toHaveBeenCalledWith(
      expect.objectContaining({
        effectiveExecutionStatus: 'running',
        isInitialized: true,
        preResolvedNodes: new Set(['task-1']),
      })
    )
    expect(mockUseEdgeExecutionStatus).toHaveBeenCalledWith(
      expect.objectContaining({
        effectiveExecutionStatus: 'running',
        storedEdges: [],
      })
    )
    expect(mockUseButtonEdgeMaintenance).toHaveBeenCalledWith(
      expect.objectContaining({
        pendingEdge: { sourceNodeId: 'task-1', x: 0, y: 0 },
      })
    )
  })
})
