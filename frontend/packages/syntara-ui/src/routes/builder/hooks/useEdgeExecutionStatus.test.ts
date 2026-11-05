import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { EdgeConnection } from '../types/edge'
import type { EdgeType } from '../utils/workflowToGraph'

import { projectEdgeExecutionStatus } from './useEdgeExecutionStatus'

const mockDetermineEdgeStatus = vi.hoisted(() => vi.fn().mockReturnValue('pending'))

vi.mock('./useBuilderFlowGraph', () => ({
  executionStateEnricher: {
    determineEdgeStatus: (...args: unknown[]) => mockDetermineEdgeStatus(...args) as unknown,
  },
}))

function makeEdge(id: string, executionStatus?: string): EdgeType {
  return {
    id,
    source: 'a',
    target: 'b',
    data: executionStatus !== undefined ? { executionStatus } : {},
  } as EdgeType
}

const activityStates = new Map<string, never>()
const storedEdges = [{ id: 'stored-edge', source: 'a', target: 'b' }] as EdgeConnection[]

beforeEach(() => {
  vi.clearAllMocks()
  mockDetermineEdgeStatus.mockReturnValue('pending')
})

describe('projectEdgeExecutionStatus', () => {
  it('preserves clean edges when execution status is inactive', () => {
    const edges = [makeEdge('e1')]

    expect(
      projectEdgeExecutionStatus(edges, {
        effectiveExecutionStatus: null,
        currentWorkflow: null,
        activityStates,
        storedEdges,
      })
    ).toBe(edges)
    expect(mockDetermineEdgeStatus).not.toHaveBeenCalled()
  })

  it('clears status overlays outside active execution and execution detail views', () => {
    const edges = [makeEdge('e1', 'passed')]
    const result = projectEdgeExecutionStatus(edges, {
      effectiveExecutionStatus: 'completed',
      currentWorkflow: null,
      activityStates,
      storedEdges,
    })

    expect(result[0].data?.executionStatus).toBeUndefined()
    expect(result[0]).not.toBe(edges[0])
  })

  it('projects execution status during active runs using workflow trigger IDs and stored edges', () => {
    const edge = makeEdge('e1')
    const workflow = {
      triggers: [{ id: 'real-trigger-1' }, { id: 'real-trigger-2' }],
      workflow: { activities: [] },
    }
    mockDetermineEdgeStatus.mockReturnValue('passed')

    const result = projectEdgeExecutionStatus([edge], {
      effectiveExecutionStatus: 'running',
      currentWorkflow: workflow as never,
      activityStates,
      storedEdges,
    })

    expect(result[0].data?.executionStatus).toBe('passed')
    expect(mockDetermineEdgeStatus).toHaveBeenCalledWith({
      edge,
      activityStates,
      activities: [],
      triggerDisplayToRealId: new Map([
        ['trigger-0', 'real-trigger-1'],
        ['trigger-1', 'real-trigger-2'],
      ]),
      edges: storedEdges,
    })
  })

  it('projects terminal run status in an execution detail view', () => {
    const edges = [makeEdge('e1')]
    mockDetermineEdgeStatus.mockReturnValue('passed')

    const result = projectEdgeExecutionStatus(edges, {
      effectiveExecutionStatus: 'completed',
      currentWorkflow: null,
      activityStates,
      storedEdges,
      isExecutionDetailView: true,
    })

    expect(result[0].data?.executionStatus).toBe('passed')
  })

  it('preserves edge and array references when the computed status is unchanged', () => {
    const edge = makeEdge('e1', 'pending')
    const edges = [edge]

    expect(
      projectEdgeExecutionStatus(edges, {
        effectiveExecutionStatus: 'running',
        currentWorkflow: null,
        activityStates,
        storedEdges,
      })
    ).toBe(edges)
  })
})
