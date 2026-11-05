import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../../workflows/execution/types'
import type { EdgeConnection } from '../types/edge'

import { projectExecutionState } from './useExecutionStateEnrichment'

const mockEnrichTriggerNode = vi.hoisted(() => vi.fn())
const mockEnrichActivity = vi.hoisted(() => vi.fn())

vi.mock('./useBuilderFlowGraph', () => ({
  executionStateEnricher: {
    enrichTriggerNode: (...args: unknown[]) => mockEnrichTriggerNode(...args) as unknown as Record<string, unknown>,
    enrichActivity: (...args: unknown[]) => mockEnrichActivity(...args) as unknown as Record<string, unknown>,
  },
}))

const activity: ActivityState = { activityId: 'task-1', status: 'running' }
const sampleActivity = { id: 'task-1', type: 'script', name: 'Task', parameters: {} }
const sampleWorkflow = {
  workflow: { activities: [sampleActivity] },
  triggers: [],
} as unknown as WorkflowDefinition
const storedEdges = [{ id: 'edge-1', source: 'trigger-0', target: 'task-1' }] as EdgeConnection[]
const baseNode = { id: 'task-1', position: { x: 0, y: 0 }, data: sampleActivity } as unknown as NodeType

beforeEach(() => vi.clearAllMocks())

describe('projectExecutionState', () => {
  it('clears the execution state overlay when execution mode ends', () => {
    const node = {
      ...baseNode,
      data: { __executionState: { status: 'completed' }, label: 'Task' },
    } as NodeType

    const result = projectExecutionState([node], {
      effectiveExecutionStatus: null,
      currentWorkflow: null,
      activityStates: new Map(),
      storedEdges,
      preResolvedNodes: new Set(),
    })

    expect(result[0].data).toEqual({ label: 'Task' })
  })

  it('enriches activity nodes using stored workflow edges and execution state', () => {
    mockEnrichActivity.mockReturnValue({ ...sampleActivity, __executionState: { status: 'running' } })

    const result = projectExecutionState([baseNode], {
      effectiveExecutionStatus: 'running',
      currentWorkflow: sampleWorkflow,
      activityStates: new Map([['task-1', activity]]),
      storedEdges,
      preResolvedNodes: new Set(['task-1']),
      copiedRunActivityIds: new Set(['task-1']),
    })

    expect(mockEnrichActivity).toHaveBeenCalledWith({
      activity: sampleActivity,
      executionStatus: 'running',
      activityStates: new Map([['task-1', activity]]),
      edges: storedEdges,
      options: { preResolvedNodes: new Set(['task-1']), skipInferenceActivityIds: new Set(['task-1']) },
    })
    expect((result[0].data as Record<string, unknown>).__executionState).toEqual({ status: 'running' })
  })

  it('derives execution overlays even before activity records have arrived', () => {
    mockEnrichActivity.mockReturnValue({ ...sampleActivity, __executionState: { status: 'pending' } })

    const result = projectExecutionState([baseNode], {
      effectiveExecutionStatus: 'running',
      currentWorkflow: sampleWorkflow,
      activityStates: new Map(),
      storedEdges,
      preResolvedNodes: new Set(),
    })

    expect((result[0].data as Record<string, unknown>).__executionState).toEqual({ status: 'pending' })
  })

  it('does not replace nodes when their execution snapshot did not change', () => {
    mockEnrichActivity.mockReturnValue({ ...sampleActivity, __executionState: { status: 'running' } })
    const node = {
      ...baseNode,
      data: { ...sampleActivity, __executionState: { status: 'running' } },
    } as unknown as NodeType
    const nodes = [node]

    expect(
      projectExecutionState(nodes, {
        effectiveExecutionStatus: 'running',
        currentWorkflow: sampleWorkflow,
        activityStates: new Map(),
        storedEdges,
        preResolvedNodes: new Set(),
      })
    ).toBe(nodes)
  })
})
