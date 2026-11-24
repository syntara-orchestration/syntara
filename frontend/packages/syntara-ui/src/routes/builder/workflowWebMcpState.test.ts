import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useWorkflowStore } from '../../stores/useWorkflowStore'

import { getWorkflowSnapshot } from './workflowWebMcpState'

vi.mock('../../stores/useWorkflowStore', () => ({ useWorkflowStore: { getState: vi.fn() } }))

const getState = vi.mocked(useWorkflowStore.getState)

describe('getWorkflowSnapshot', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns the current workflow, canvas state, and default activity lists', () => {
    const store = {
      currentWorkflow: { workflow: { activities: [{ id: 'step-1' }] }, triggers: [{ id: 'trigger-1' }] },
      edges: [{ id: 'edge-1' }],
      nodePositions: { 'step-1': { x: 1, y: 2 } },
    }
    getState.mockReturnValue(store as never)
    expect(getWorkflowSnapshot()).toEqual({
      store,
      currentWorkflow: store.currentWorkflow,
      activities: [{ id: 'step-1' }],
      triggers: [{ id: 'trigger-1' }],
      edges: store.edges,
      nodePositions: store.nodePositions,
    })
  })

  it('uses empty arrays while the workflow is not loaded', () => {
    const store = { currentWorkflow: null, edges: [], nodePositions: {} }
    getState.mockReturnValue(store as never)
    expect(getWorkflowSnapshot()).toMatchObject({ currentWorkflow: null, activities: [], triggers: [], edges: [] })
  })
})
