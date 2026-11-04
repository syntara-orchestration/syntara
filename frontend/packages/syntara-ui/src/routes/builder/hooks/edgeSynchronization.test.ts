import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { EdgeType } from '../utils/workflowToGraph'

import { getSynchronizedEdgeConnections, synchronizeBuilderFlowEdges } from './edgeSynchronization'

const mocks = vi.hoisted(() => ({
  storeState: {
    currentWorkflow: { triggers: [] as Array<{ id: string }> },
    _temporalBatchPending: false,
    reorderActivitiesFromEdges: vi.fn(),
  },
  setState: vi.fn(),
  resumeTemporal: vi.fn(),
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => mocks.storeState),
    setState: (updates: Record<string, unknown>) => {
      mocks.setState(updates)
      Object.assign(mocks.storeState, updates)
    },
    temporal: { getState: () => ({ resume: mocks.resumeTemporal }) },
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.storeState.currentWorkflow = { triggers: [] }
  mocks.storeState._temporalBatchPending = false
})

describe('getSynchronizedEdgeConnections', () => {
  it('filters button, placeholder, and pending edges', () => {
    const edges: EdgeType[] = [
      { id: 'edge-1', source: 'node-1', target: 'node-2' },
      { id: 'button-1', source: 'node-1', target: 'placeholder-1', type: 'buttonEdge' },
      { id: 'placeholder-source', source: 'placeholder-1', target: 'node-2' },
      { id: 'pending-edge', source: 'node-1', target: 'node-3' },
      { id: 'pending-target-edge', source: 'pending-target-1', target: 'node-4' },
    ]

    expect(getSynchronizedEdgeConnections(edges, [])).toEqual([
      { id: 'edge-1', source: 'node-1', target: 'node-2', sourceHandle: undefined, targetHandle: undefined },
    ])
  })

  it('maps trigger display IDs to canonical trigger IDs and preserves handles', () => {
    const edges: EdgeType[] = [
      {
        id: 'edge-1',
        source: 'trigger-0',
        target: 'trigger-1',
        sourceHandle: 'source',
        targetHandle: 'target',
      },
    ]

    expect(getSynchronizedEdgeConnections(edges, [{ id: 'trigger-real-1' }, { id: 'trigger-real-2' }])).toEqual([
      {
        id: 'edge-1',
        source: 'trigger-real-1',
        target: 'trigger-real-2',
        sourceHandle: 'source',
        targetHandle: 'target',
      },
    ])
  })

  it('leaves unresolved trigger display IDs unchanged', () => {
    const edges: EdgeType[] = [{ id: 'edge-1', source: 'trigger-2', target: 'node-1' }]

    expect(getSynchronizedEdgeConnections(edges, [{ id: 'trigger-real-1' }])[0].source).toBe('trigger-2')
  })

  it('waits for initialization and active execution to clear before synchronizing', () => {
    const state = { lastEdgesSignature: '', isSyncing: false, isFirstSync: true }
    const setStoredEdges = vi.fn()
    const edges: EdgeType[] = [{ id: 'edge-1', source: 'node-1', target: 'node-2' }]

    synchronizeBuilderFlowEdges({ edges, isInitialized: false, isActiveExecution: false, state, setStoredEdges })
    synchronizeBuilderFlowEdges({ edges, isInitialized: true, isActiveExecution: true, state, setStoredEdges })

    expect(setStoredEdges).not.toHaveBeenCalled()
    expect(state.isFirstSync).toBe(true)
  })

  it('records the first signature, deduplicates unchanged edges, then syncs changed edges once', async () => {
    const state = { lastEdgesSignature: '', isSyncing: false, isFirstSync: true }
    const setStoredEdges = vi.fn()
    const firstEdges: EdgeType[] = [{ id: 'edge-1', source: 'node-1', target: 'node-2' }]
    const nextEdges: EdgeType[] = [{ id: 'edge-2', source: 'node-2', target: 'node-3' }]

    synchronizeBuilderFlowEdges({
      edges: firstEdges,
      isInitialized: true,
      isActiveExecution: false,
      state,
      setStoredEdges,
    })
    synchronizeBuilderFlowEdges({
      edges: firstEdges,
      isInitialized: true,
      isActiveExecution: false,
      state,
      setStoredEdges,
    })
    expect(setStoredEdges).not.toHaveBeenCalled()

    synchronizeBuilderFlowEdges({
      edges: nextEdges,
      isInitialized: true,
      isActiveExecution: false,
      state,
      setStoredEdges,
    })
    expect(setStoredEdges).toHaveBeenCalledTimes(1)
    expect(mocks.storeState.reorderActivitiesFromEdges).toHaveBeenCalledTimes(1)
    expect(state.isSyncing).toBe(true)

    synchronizeBuilderFlowEdges({
      edges: [{ id: 'edge-3', source: 'node-3', target: 'node-4' }],
      isInitialized: true,
      isActiveExecution: false,
      state,
      setStoredEdges,
    })
    expect(setStoredEdges).toHaveBeenCalledTimes(1)

    await new Promise<void>((resolve) => queueMicrotask(resolve))
    expect(state.isSyncing).toBe(false)
  })

  it('resumes a pending temporal batch after writing edges and reordering activities', () => {
    mocks.storeState._temporalBatchPending = true
    const state = { lastEdgesSignature: 'previous', isSyncing: false, isFirstSync: false }
    const setStoredEdges = vi.fn()

    synchronizeBuilderFlowEdges({
      edges: [{ id: 'edge-2', source: 'node-2', target: 'node-3' }],
      isInitialized: true,
      isActiveExecution: false,
      state,
      setStoredEdges,
    })

    expect(setStoredEdges).toHaveBeenCalledTimes(1)
    expect(mocks.storeState.reorderActivitiesFromEdges).toHaveBeenCalledTimes(1)
    expect(mocks.setState).toHaveBeenCalledWith({ _temporalBatchPending: false })
    expect(mocks.resumeTemporal).toHaveBeenCalledTimes(1)
    expect(mocks.storeState._temporalBatchPending).toBe(false)
  })
})
