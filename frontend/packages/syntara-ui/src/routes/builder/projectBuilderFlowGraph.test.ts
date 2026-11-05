import { ActivityTypeEnum } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../constants'
import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../workflows/execution/types'

import type { ValidationError } from './builderReducer'
import { projectBuilderFlowGraph } from './projectBuilderFlowGraph'
import type { EdgeConnection } from './types/edge'
import type { EdgeType } from './utils/workflowToGraph'

vi.mock('./hooks/useLoopBackNodeTypes', () => ({
  projectLoopBackNodeTypes: (nodes: NodeType[]) =>
    nodes.map((node) =>
      node.id === 'task-1'
        ? {
            ...node,
            type: 'task-reversed',
            data: {
              ...node.data,
              metadata: {
                ...((node.data as Record<string, unknown>).metadata as Record<string, unknown> | undefined),
                __reverseHandles: true,
              },
            },
          }
        : node
    ),
}))

describe('projectBuilderFlowGraph', () => {
  it('composes view-only node and edge data over untouched controlled graph state', () => {
    const trigger = {
      id: 'trigger-0',
      type: FlowNodeType.TRIGGER,
      position: { x: 0, y: 0 },
      data: { definitionId: 'trigger-manual', name: 'Manual', triggerType: 'manual_trigger' },
    } as unknown as NodeType
    const taskActivity = {
      id: 'task-1',
      type: ActivityTypeEnum.SCRIPT,
      name: 'Task',
      parameters: {},
      metadata: {},
    }
    const task = {
      id: 'task-1',
      type: FlowNodeType.TASK,
      position: { x: 100, y: 0 },
      data: taskActivity,
    } as unknown as NodeType
    const nextTaskActivity = {
      id: 'task-2',
      type: ActivityTypeEnum.SCRIPT,
      name: 'Next task',
      parameters: {},
    }
    const nextTask = {
      id: 'task-2',
      type: FlowNodeType.TASK,
      position: { x: 200, y: 0 },
      data: nextTaskActivity,
    } as unknown as NodeType
    const rawNodes = [trigger, task, nextTask]
    const rawEdges = [{ id: 'edge-1', type: 'default', source: 'task-1', target: 'task-2' }] as EdgeType[]
    const currentWorkflow = {
      triggers: [{ id: 'trigger-manual' }],
      workflow: { activities: [taskActivity, nextTaskActivity] },
    } as unknown as WorkflowDefinition
    const activityStates = new Map<string, ActivityState>([
      ['task-1', { activityId: 'task-1', status: 'completed' }],
      ['task-2', { activityId: 'task-2', status: 'running' }],
    ])
    const storedEdges = [{ id: 'edge-1', source: 'task-1', target: 'task-2' }] as EdgeConnection[]
    const validationErrors: ValidationError[] = [{ message: 'Task needs input', nodeId: 'task-1' }]
    const onAddNodeFromEdge = vi.fn()

    const projected = projectBuilderFlowGraph({
      nodes: rawNodes,
      edges: rawEdges,
      isInitialized: true,
      selectedActivityId: 'task-1',
      activeEdgeId: 'edge-1',
      onAddNodeFromEdge,
      pendingEdge: null,
      buttonEdgeExecutionStatus: null,
      isReadOnly: false,
      effectiveExecutionStatus: 'running',
      isExecutionDetailView: false,
      currentWorkflow,
      activityStates,
      storedEdges,
      triggers: [{ id: 'trigger-manual' }],
      preResolvedNodes: new Set(),
      validationErrors,
    })

    const projectedTask = projected.nodes.find((node) => node.id === 'task-1')
    expect(projectedTask?.selected).toBe(true)
    expect(projectedTask?.type).toBe(FlowNodeType.TASK_REVERSED)
    expect(projectedTask?.data).toMatchObject({
      __executionState: { status: 'completed' },
      __validationError: true,
      metadata: { __reverseHandles: true, __showExecutionBadge: true },
    })
    expect(projected.edges[0].markerEnd).toBeDefined()
    expect(projected.edges[0]).toMatchObject({
      data: { isActive: true, executionStatus: 'passed', onAddNode: onAddNodeFromEdge },
    })

    expect(task.type).toBe(FlowNodeType.TASK)
    expect(task.data).toEqual(taskActivity)
    expect(rawEdges[0].data).toBeUndefined()
    expect(rawEdges[0].markerEnd).toBeUndefined()
    expect(projected.nodes.some((node) => node.id === 'placeholder-task-2')).toBe(true)
    expect(projected.edges.some((edge) => edge.id === 'button-task-2')).toBe(true)
  })

  it('projects pending edge creation and cancellation without changing raw graph state', () => {
    const task = {
      id: 'task-1',
      type: FlowNodeType.TASK,
      position: { x: 20, y: 30 },
      data: { id: 'task-1', type: ActivityTypeEnum.SCRIPT, name: 'Task', parameters: {} },
    } as unknown as NodeType
    const rawNodes = [task]
    const rawEdges: EdgeType[] = []
    const baseOptions = {
      nodes: rawNodes,
      edges: rawEdges,
      isInitialized: true,
      effectiveExecutionStatus: null,
      isExecutionDetailView: false,
      currentWorkflow: null,
      activityStates: new Map<string, ActivityState>(),
      storedEdges: [],
      triggers: [],
      preResolvedNodes: new Set<string>(),
      buttonEdgeExecutionStatus: null,
      isReadOnly: false,
    }
    const pending = projectBuilderFlowGraph({
      ...baseOptions,
      pendingEdge: { sourceNodeId: 'task-1', x: 300, y: 200 },
    })

    expect(pending.nodes.some((node) => node.id === 'pending-target-task-1')).toBe(true)
    expect(pending.edges.some((edge) => edge.id === 'pending-task-1')).toBe(true)
    expect(pending.edges.some((edge) => edge.id === 'button-task-1')).toBe(false)

    const cancelled = projectBuilderFlowGraph({ ...baseOptions, pendingEdge: null })
    expect(cancelled.nodes.some((node) => node.id === 'pending-target-task-1')).toBe(false)
    expect(cancelled.edges.some((edge) => edge.id === 'pending-task-1')).toBe(false)
    expect(cancelled.edges.some((edge) => edge.id === 'button-task-1')).toBe(true)
    expect(task.data).toEqual({ id: 'task-1', type: ActivityTypeEnum.SCRIPT, name: 'Task', parameters: {} })
    expect(rawEdges).toEqual([])
  })
})
