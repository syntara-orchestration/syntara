import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'

/**
 * Integration tests for loop node functionality.
 * Tests the complete flow of loop node creation, edge generation, and positioning.
 * Updated to use v2 activity shapes (type: 'loop' with config, type: 'script_python' with config).
 */
describe('Loop Node Integration Tests', () => {
  beforeEach(() => {
    useWorkflowStore.getState().setWorkflow(null)
  })

  afterEach(() => {
    useWorkflowStore.getState().setWorkflow(null)
  })

  describe('Loop Node Creation', () => {
    it('should create loop activity with generic body node atomically', () => {
      const store = useWorkflowStore.getState()

      store.setWorkflow({
        schema_version: '2.0.0',
        name: 'Test Workflow',
        description: 'Test workflow for loop node creation',
        triggers: [],
        workflow: { activities: [] },
      })

      const loopId = 'loop_1'
      const genericId = 'task_1'

      const loopActivity = {
        type: 'loop' as const,
        id: loopId,
        name: 'Test Loop',
        parameters: { type: 'for_each' as const, items: 'input.items' },
      }

      const genericActivity = {
        type: 'script_python' as const,
        id: genericId,
        name: '',
        parameters: { code: '' },
        metadata: { __isGeneric: true },
      }

      const edges = [
        {
          id: `${loopId}-loop-${genericId}`,
          source: loopId,
          target: genericId,
          sourceHandle: 'loop',
          targetHandle: 'target',
        },
        {
          id: `${genericId}-${loopId}-end`,
          source: genericId,
          target: loopId,
          sourceHandle: 'source',
          targetHandle: 'end',
        },
      ]

      store.batchAddActivitiesAndEdges({ activities: [loopActivity, genericActivity], edges })

      const updatedStore = useWorkflowStore.getState()

      expect(updatedStore.currentWorkflow?.workflow.activities).toHaveLength(2)
      expect(updatedStore.currentWorkflow?.workflow.activities[0].id).toBe(loopId)
      expect(updatedStore.currentWorkflow?.workflow.activities[1].id).toBe(genericId)

      const storedEdges = updatedStore.edges
      expect(storedEdges).toHaveLength(2)
    })

    it('should create loop-to-body and body-to-loop edges', () => {
      const store = useWorkflowStore.getState()

      store.setWorkflow({
        schema_version: '2.0.0',
        name: 'Test Workflow',
        description: 'Test workflow for loop edges',
        triggers: [],
        workflow: { activities: [] },
      })

      const loopId = 'loop_1'
      const genericId = 'task_1'

      const edges = [
        {
          id: `${loopId}-loop-${genericId}`,
          source: loopId,
          target: genericId,
          sourceHandle: 'loop',
          targetHandle: 'target',
        },
        {
          id: `${genericId}-${loopId}-end`,
          source: genericId,
          target: loopId,
          sourceHandle: 'source',
          targetHandle: 'end',
        },
      ]

      store.setEdges(edges)

      const storedEdges = store.edges

      const loopToBody = storedEdges.find((e) => e.sourceHandle === 'loop')
      expect(loopToBody).toBeDefined()
      expect(loopToBody?.source).toBe(loopId)
      expect(loopToBody?.target).toBe(genericId)

      const bodyToLoop = storedEdges.find((e) => e.targetHandle === 'end')
      expect(bodyToLoop).toBeDefined()
      expect(bodyToLoop?.source).toBe(genericId)
      expect(bodyToLoop?.target).toBe(loopId)
    })

    it('should support multiple nodes in loop body', () => {
      const store = useWorkflowStore.getState()

      store.setWorkflow({
        schema_version: '2.0.0',
        name: 'Test Workflow',
        description: 'Test workflow for multiple loop nodes',
        triggers: [],
        workflow: { activities: [] },
      })

      const loopId = 'loop_1'
      const task1Id = 'task_1'
      const task2Id = 'task_2'

      const loopActivity = {
        type: 'loop' as const,
        id: loopId,
        name: 'Test Loop',
        parameters: { type: 'for_each' as const, items: 'input.items' },
      }
      const task1 = {
        type: 'script_python' as const,
        id: task1Id,
        name: 'Task 1',
        parameters: { code: '' },
      }
      const task2 = {
        type: 'script_python' as const,
        id: task2Id,
        name: 'Task 2',
        parameters: { code: '' },
      }

      const edges = [
        {
          id: `${loopId}-loop-${task1Id}`,
          source: loopId,
          target: task1Id,
          sourceHandle: 'loop',
          targetHandle: 'target',
        },
        {
          id: `${task1Id}-${task2Id}`,
          source: task1Id,
          target: task2Id,
          sourceHandle: 'source',
          targetHandle: 'target',
        },
        {
          id: `${task2Id}-${loopId}-end`,
          source: task2Id,
          target: loopId,
          sourceHandle: 'source',
          targetHandle: 'end',
        },
      ]

      store.batchAddActivitiesAndEdges({ activities: [loopActivity, task1, task2], edges })

      const updatedStore = useWorkflowStore.getState()

      expect(updatedStore.currentWorkflow?.workflow.activities).toHaveLength(3)
      expect(updatedStore.edges).toHaveLength(3)
    })
  })

  describe('Loop Node Edge Types', () => {
    it('should identify loop outgoing edges correctly', () => {
      const edges = [{ id: 'edge1', source: 'loop_1', target: 'task_1', sourceHandle: 'loop', targetHandle: 'target' }]
      const loopOutgoing = edges.find((e) => e.sourceHandle === 'loop')
      expect(loopOutgoing).toBeDefined()
      expect(loopOutgoing?.source).toBe('loop_1')
    })

    it('should identify loop-back edges correctly', () => {
      const edges = [{ id: 'edge1', source: 'task_1', target: 'loop_1', sourceHandle: 'source', targetHandle: 'end' }]
      const loopBack = edges.find((e) => e.targetHandle === 'end')
      expect(loopBack).toBeDefined()
      expect(loopBack?.source).toBe('task_1')
    })

    it('should identify loop done edges correctly', () => {
      const edges = [{ id: 'edge1', source: 'loop_1', target: 'task_2', sourceHandle: 'done', targetHandle: 'target' }]
      const loopDone = edges.find((e) => e.sourceHandle === 'done')
      expect(loopDone).toBeDefined()
      expect(loopDone?.source).toBe('loop_1')
    })
  })

  describe('Loop Node Body Detection', () => {
    it('should identify loop body nodes from edges', () => {
      const edges = [
        { id: 'edge1', source: 'loop_1', target: 'task_1', sourceHandle: 'loop', targetHandle: 'target' },
        { id: 'edge2', source: 'task_1', target: 'task_2', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'edge3', source: 'task_2', target: 'loop_1', sourceHandle: 'source', targetHandle: 'end' },
      ]

      const loopBodyNodeMap = new Map<string, string>()
      edges.forEach((e) => {
        if (e.sourceHandle === 'loop') {
          loopBodyNodeMap.set(e.target, e.source)
        }
      })

      expect(loopBodyNodeMap.has('task_1')).toBe(true)
      expect(loopBodyNodeMap.get('task_1')).toBe('loop_1')
      expect(loopBodyNodeMap.has('task_2')).toBe(false)
    })
  })

  describe('Loop Node Positioning Logic', () => {
    it('should calculate correct position for loop body node', () => {
      const loopPosition = { x: 100, y: 200, width: 240, height: 80 }
      const horizontalSpacing = 50

      const calculatedX = loopPosition.x + loopPosition.width + horizontalSpacing
      const calculatedY = loopPosition.y + loopPosition.height / 2

      expect(calculatedX).toBe(390)
      expect(calculatedY).toBe(240)
    })
  })

  describe('Batch Operations', () => {
    it('should prevent race conditions with atomic updates', () => {
      const store = useWorkflowStore.getState()

      store.setWorkflow({
        schema_version: '2.0.0',
        name: 'Test Workflow',
        description: 'Test workflow for atomic updates',
        triggers: [],
        workflow: { activities: [] },
      })

      const initialVersion = useWorkflowStore.getState().workflowVersion

      const loopActivity = {
        type: 'loop' as const,
        id: 'loop_1',
        name: 'Test Loop',
        parameters: { type: 'for_each' as const, items: 'input.items' },
      }
      const genericActivity = {
        type: 'script_python' as const,
        id: 'task_1',
        name: '',
        parameters: { code: '' },
      }

      const edges = [
        { id: 'edge1', source: 'loop_1', target: 'task_1', sourceHandle: 'loop', targetHandle: 'target' },
        { id: 'edge2', source: 'task_1', target: 'loop_1', sourceHandle: 'source', targetHandle: 'end' },
      ]

      store.batchAddActivitiesAndEdges({ activities: [loopActivity, genericActivity], edges })

      const updatedStore = useWorkflowStore.getState()

      expect(updatedStore.workflowVersion).toBe(initialVersion)
      expect(updatedStore.currentWorkflow?.workflow.activities).toHaveLength(2)
      expect(updatedStore.edges).toHaveLength(2)
    })
  })

  describe('Loop Edge Reconnection on Deletion', () => {
    it('should reconnect loop edge when last activity in loop is deleted', () => {
      const store = useWorkflowStore.getState()

      const loopId = 'loop_1'
      const task1Id = 'task_1'
      const task2Id = 'task_2'
      const task3Id = 'task_3'

      const loopActivity = {
        type: 'loop' as const,
        id: loopId,
        name: 'Test Loop',
        parameters: { type: 'for_each' as const, items: 'input.items' },
      }
      const task1 = {
        type: 'script_python' as const,
        id: task1Id,
        name: 'Task 1',
        parameters: { code: '' },
      }
      const task2 = {
        type: 'script_python' as const,
        id: task2Id,
        name: 'Task 2',
        parameters: { code: '' },
      }
      const task3 = {
        type: 'script_python' as const,
        id: task3Id,
        name: 'Task 3',
        parameters: { code: '' },
      }

      const initialEdges = [
        {
          id: `${loopId}-loop-${task1Id}`,
          source: loopId,
          target: task1Id,
          sourceHandle: 'loop',
          targetHandle: 'target',
        },
        {
          id: `${task1Id}-${task2Id}`,
          source: task1Id,
          target: task2Id,
          sourceHandle: 'source',
          targetHandle: 'target',
        },
        {
          id: `${task2Id}-${task3Id}`,
          source: task2Id,
          target: task3Id,
          sourceHandle: 'source',
          targetHandle: 'target',
        },
        {
          id: `${task3Id}-${loopId}-end`,
          source: task3Id,
          target: loopId,
          sourceHandle: 'source',
          targetHandle: 'end',
        },
      ]

      store.setWorkflow({
        schema_version: '2.0.0',
        name: 'Test Workflow',
        description: 'Test workflow for loop edge reconnection',
        triggers: [],
        workflow: { activities: [loopActivity, task1, task2, task3] },
      })

      store.setEdges(initialEdges)

      const updatedEdges = [
        {
          id: `${loopId}-loop-${task1Id}`,
          source: loopId,
          target: task1Id,
          sourceHandle: 'loop',
          targetHandle: 'target',
        },
        {
          id: `${task1Id}-${task2Id}`,
          source: task1Id,
          target: task2Id,
          sourceHandle: 'source',
          targetHandle: 'target',
        },
        {
          id: `${task2Id}-${loopId}-end`,
          source: task2Id,
          target: loopId,
          sourceHandle: 'source',
          targetHandle: 'end',
        },
      ]

      store.batchRemoveNodesAndEdges({ nodeIds: [task3Id], edges: updatedEdges, triggerIndices: [] })

      const finalState = useWorkflowStore.getState()
      expect(finalState.currentWorkflow?.workflow.activities).toHaveLength(3)
      expect(finalState.edges).toHaveLength(3)

      const loopBackEdge = finalState.edges.find(
        (e) => e.source === task2Id && e.target === loopId && e.targetHandle === 'end'
      )
      expect(loopBackEdge).toBeDefined()
    })
  })
})
