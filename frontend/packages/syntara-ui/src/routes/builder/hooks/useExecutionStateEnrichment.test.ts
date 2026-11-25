import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../../workflows/execution/types'

import { useExecutionStateEnrichment } from './useExecutionStateEnrichment'

const runningActivityState = (activityId: string): ActivityState => ({
  activityId,
  status: 'running',
})

const mockEnrichTriggerNode = vi.fn()
const mockEnrichActivity = vi.fn()

vi.mock('./useBuilderFlowGraph', () => ({
  executionStateEnricher: {
    enrichTriggerNode: (...args: unknown[]) => mockEnrichTriggerNode(...args) as Record<string, unknown>,
    enrichActivity: (...args: unknown[]) => mockEnrichActivity(...args) as Record<string, unknown>,
  },
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: () => ({ edges: [] }),
  },
}))

const baseNode = { id: 'task-1', position: { x: 0, y: 0 }, data: {} } as NodeType
const sampleActivity = { id: 'task-1', type: 'script_python', name: 'Task', parameters: {} }

const sampleWorkflow = {
  workflow: { activities: [sampleActivity] },
  triggers: [],
} as unknown as WorkflowDefinition

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useExecutionStateEnrichment', () => {
  it('does nothing when not initialized', () => {
    const setNodes = vi.fn()
    renderHook(() =>
      useExecutionStateEnrichment({
        effectiveExecutionStatus: 'running',
        isInitialized: false,
        currentWorkflow: null,
        activityStates: new Map([['task-1', runningActivityState('task-1')]]),
        preResolvedNodes: new Set(),
        setNodes,
      })
    )

    expect(setNodes).not.toHaveBeenCalled()
  })

  it('clears execution state when leaving execution mode', () => {
    const setNodes = vi.fn()
    const nodeWithState = {
      ...baseNode,
      data: { __executionState: { status: 'completed' }, label: 'Task' },
    } as NodeType

    renderHook(() =>
      useExecutionStateEnrichment({
        effectiveExecutionStatus: null,
        isInitialized: true,
        currentWorkflow: null,
        activityStates: new Map(),
        preResolvedNodes: new Set(),
        setNodes,
      })
    )

    expect(setNodes).toHaveBeenCalledTimes(1)
    const updater = setNodes.mock.calls[0][0] as (nodes: NodeType[]) => NodeType[]
    const updated = updater([nodeWithState])
    expect(updated[0].data).toEqual({ label: 'Task' })
  })

  it('enriches activity nodes when execution is active', () => {
    const setNodes = vi.fn()
    mockEnrichActivity.mockReturnValue({ label: 'Task', __executionState: { status: 'running' } })

    renderHook(() =>
      useExecutionStateEnrichment({
        effectiveExecutionStatus: 'running',
        isInitialized: true,
        currentWorkflow: sampleWorkflow,
        activityStates: new Map([['task-1', runningActivityState('task-1')]]),
        preResolvedNodes: new Set(),
        setNodes,
      })
    )

    expect(setNodes).toHaveBeenCalledTimes(1)
    const updater = setNodes.mock.calls[0][0] as (nodes: NodeType[]) => NodeType[]
    const updated = updater([baseNode])
    expect(mockEnrichActivity).toHaveBeenCalled()
    expect((updated[0].data as Record<string, unknown>).__executionState).toEqual({ status: 'running' })
  })

  it('updates a trigger node when only reused input status changes', () => {
    const setNodes = vi.fn()
    const sourceTimestamp = '2024-01-01T10:00:00Z'
    const triggerNode = {
      ...baseNode,
      id: 'trigger-0',
      data: {
        __executionState: {
          status: 'completed',
          started_at: sourceTimestamp,
          replayed: false,
          retainedFailure: false,
          triggerInputReused: false,
        },
      },
    } as NodeType
    mockEnrichTriggerNode.mockReturnValue({
      label: 'Manual Trigger',
      __executionState: {
        status: 'completed',
        started_at: sourceTimestamp,
        replayed: false,
        retainedFailure: false,
        triggerInputReused: true,
      },
    })

    renderHook(() =>
      useExecutionStateEnrichment({
        effectiveExecutionStatus: 'running',
        isInitialized: true,
        currentWorkflow: {
          ...sampleWorkflow,
          triggers: [{ id: 'manual-trigger', type: 'manual', name: 'Manual Trigger' }],
        } as unknown as WorkflowDefinition,
        activityStates: new Map([
          ['manual-trigger', { ...runningActivityState('manual-trigger'), status: 'completed' }],
        ]),
        preResolvedNodes: new Set(),
        replayBaselineAt: '2024-01-01T10:02:00Z',
        setNodes,
      })
    )

    const updateNodes = setNodes.mock.calls[0][0] as (nodes: NodeType[]) => NodeType[]
    const updatedNodes = updateNodes([triggerNode])

    expect(updatedNodes[0]).not.toBe(triggerNode)
    expect((updatedNodes[0].data as Record<string, unknown>).__executionState).toMatchObject({
      triggerInputReused: true,
    })
  })

  it('skips enrichment when activityStates is empty', () => {
    const setNodes = vi.fn()
    renderHook(() =>
      useExecutionStateEnrichment({
        effectiveExecutionStatus: 'running',
        isInitialized: true,
        currentWorkflow: { ...sampleWorkflow, triggers: undefined },
        activityStates: new Map(),
        preResolvedNodes: new Set(),
        setNodes,
      })
    )

    expect(setNodes).not.toHaveBeenCalled()
  })
})
