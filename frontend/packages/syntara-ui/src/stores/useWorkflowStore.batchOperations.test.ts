import { describe, expect, it, beforeEach } from 'vitest'

import type { EdgeConnection } from '../routes/builder/types/edge'

import {
  useWorkflowStore,
  createPythonScriptActivity,
  createConvergeActivity,
  createManualTrigger,
} from './useWorkflowStore'
import type { Activity, WorkflowDefinition } from './workflowStoreTypes'

// Helper to create a v2 WorkflowDefinition for tests
function makeWorkflow(name: string, activities: Activity[] = [], triggers?: Activity[]): WorkflowDefinition {
  return {
    schema_version: '2.0.0',
    name,
    description: '',
    triggers: triggers ?? [],
    workflow: { activities },
  }
}

describe('useWorkflowStore - batchRemoveNodesAndEdges', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      currentWorkflow: null,
      workflowVersion: 0,
      edges: [],
    })
  })

  describe('Atomic operations', () => {
    it('removes activities and updates edges in single transaction', () => {
      const activityA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const activityC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityA, activityB, activityC]),
        workflowVersion: 1,
        edges,
      })

      // Remove B and update edges
      const newEdges: EdgeConnection[] = [
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['B'],
        edges: newEdges,
      })

      const state = useWorkflowStore.getState()
      const activities = state.currentWorkflow?.workflow.activities ?? []

      // B should be removed
      expect(activities).toHaveLength(2)
      expect(activities.map((a) => a.id)).toEqual(['A', 'C'])

      // Edges should be updated
      expect(state.edges).toEqual(newEdges)
    })

    it('removes multiple activities at once', () => {
      const activityA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const activityC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const activityD = createPythonScriptActivity({ id: 'D', name: 'Task D', code: 'print("D")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityA, activityB, activityC, activityD]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['B', 'C'],
        edges: [],
      })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(2)
      expect(activities.map((a) => a.id)).toEqual(['A', 'D'])
    })
  })

  describe('Converge node cleanup', () => {
    it('removes converge from flat list', () => {
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const activityC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const convergeActivity = createConvergeActivity('J', 'Converge J')

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityB, activityC, convergeActivity]),
        workflowVersion: 1,
        edges: [
          { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'C-J', source: 'C', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['J'],
        edges: [],
      })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []

      // Join should be removed
      expect(activities.find((a) => a.id === 'J')).toBeUndefined()

      // Branch activities should remain
      expect(activities.find((a) => a.id === 'B')).toBeDefined()
      expect(activities.find((a) => a.id === 'C')).toBeDefined()
    })

    it('handles multiple converge removals', () => {
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const activityC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const activityD = createPythonScriptActivity({ id: 'D', name: 'Task D', code: 'print("D")' })
      const activityE = createPythonScriptActivity({ id: 'E', name: 'Task E', code: 'print("E")' })

      const convergeJ1 = createConvergeActivity('J1', 'Converge 1')
      const convergeJ2 = createConvergeActivity('J2', 'Converge 2')

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityB, activityC, convergeJ1, activityD, activityE, convergeJ2]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['J1', 'J2'],
        edges: [],
      })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []

      // All joins should be removed
      expect(activities.find((a) => a.id === 'J1')).toBeUndefined()
      expect(activities.find((a) => a.id === 'J2')).toBeUndefined()

      // All branch activities should remain
      expect(activities.map((a) => a.id).sort()).toEqual(['B', 'C', 'D', 'E'])
    })
  })

  describe('Trigger removal', () => {
    it('removes triggers by index', () => {
      const trigger1 = createManualTrigger('test-trigger-1', false)
      const trigger2 = createManualTrigger('test-trigger-2', true)
      const trigger3 = createManualTrigger('test-trigger-1', false)

      useWorkflowStore.setState({
        currentWorkflow: {
          ...makeWorkflow('Test'),
          triggers: [trigger1, trigger2, trigger3],
        },
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: [],
        edges: [],
        triggerIndices: [1], // Remove second trigger
      })

      const triggers = useWorkflowStore.getState().currentWorkflow?.triggers ?? []
      expect(triggers).toHaveLength(2)
      expect(triggers).toEqual([trigger1, trigger3])
    })

    it('removes multiple triggers', () => {
      const trigger1 = createManualTrigger('test-trigger-1', false)
      const trigger2 = createManualTrigger('test-trigger-2', true)
      const trigger3 = createManualTrigger('test-trigger-1', false)

      useWorkflowStore.setState({
        currentWorkflow: {
          ...makeWorkflow('Test'),
          triggers: [trigger1, trigger2, trigger3],
        },
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: [],
        edges: [],
        triggerIndices: [0, 2], // Remove first and third
      })

      const triggers = useWorkflowStore.getState().currentWorkflow?.triggers ?? []
      expect(triggers).toHaveLength(1)
      expect(triggers).toEqual([trigger2])
    })

    it('removes all triggers', () => {
      const trigger1 = createManualTrigger('test-trigger-1', false)
      const trigger2 = createManualTrigger('test-trigger-2', true)

      useWorkflowStore.setState({
        currentWorkflow: {
          ...makeWorkflow('Test'),
          triggers: [trigger1, trigger2],
        },
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: [],
        edges: [],
        triggerIndices: [0, 1],
      })

      const triggers = useWorkflowStore.getState().currentWorkflow?.triggers
      expect(triggers).toBeUndefined()
    })
  })

  describe('Combined operations', () => {
    it('removes both activities and triggers atomically', () => {
      const trigger1 = createManualTrigger('test-trigger-1', false)
      const trigger2 = createManualTrigger('test-trigger-2', true)
      const activityA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: {
          ...makeWorkflow('Test', [activityA, activityB]),
          triggers: [trigger1, trigger2],
        },
        workflowVersion: 1,
        edges: [{ id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' }],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['A'],
        edges: [],
        triggerIndices: [0],
      })

      const state = useWorkflowStore.getState()
      const activities = state.currentWorkflow?.workflow.activities ?? []
      const triggers = state.currentWorkflow?.triggers ?? []

      expect(activities).toHaveLength(1)
      expect(activities[0].id).toBe('B')

      expect(triggers).toHaveLength(1)
      expect(triggers[0]).toEqual(trigger2)

      expect(state.edges).toEqual([])
    })

    it('handles complex scenario with converges, triggers, and edges', () => {
      const trigger = createManualTrigger('test-trigger-1', false)
      const activityA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const activityC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const convergeActivity = createConvergeActivity('J', 'Converge J')

      useWorkflowStore.setState({
        currentWorkflow: {
          ...makeWorkflow('Test', [activityA, activityB, activityC, convergeActivity]),
          triggers: [trigger],
        },
        workflowVersion: 1,
        edges: [
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'C-J', source: 'C', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      // Remove join, A, and trigger all at once
      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['J', 'A'],
        edges: [],
        triggerIndices: [0],
      })

      const state = useWorkflowStore.getState()
      const activities = state.currentWorkflow?.workflow.activities ?? []

      // Should have B and C remaining
      expect(activities.map((a) => a.id).sort()).toEqual(['B', 'C'])
      expect(state.currentWorkflow?.triggers).toBeUndefined()
      expect(state.edges).toEqual([])
    })
  })

  describe('Nested activity removal', () => {
    it('removes activity from flat list (v2 has no nesting)', () => {
      const conditionActivity: Activity = {
        type: 'condition',
        id: 'A',
        name: 'Condition A',
        parameters: { condition: 'input.value > 10' },
      }
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const activityC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [conditionActivity, activityB, activityC]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['B'],
        edges: [],
      })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(2)
      expect(activities.map((a) => a.id)).toEqual(['A', 'C'])
    })

    it('removes entire condition with nested activities', () => {
      const conditionActivity: Activity = {
        type: 'condition',
        id: 'A',
        name: 'Condition A',
        parameters: { condition: 'input.value > 10' },
      }
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [conditionActivity, activityB]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['A'],
        edges: [],
      })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(1)
      expect(activities[0].id).toBe('B')
    })
  })

  describe('Edge cases', () => {
    it('does nothing when no workflow is set', () => {
      useWorkflowStore.setState({ currentWorkflow: null })

      expect(() =>
        useWorkflowStore.getState().batchRemoveNodesAndEdges({
          nodeIds: ['A'],
          edges: [],
        })
      ).not.toThrow()

      expect(useWorkflowStore.getState().currentWorkflow).toBeNull()
    })

    it('handles empty nodeIds array', () => {
      const activityA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityA]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: [],
        edges: [],
      })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(1)
      expect(activities[0].id).toBe('A')
    })

    it('handles non-existent node IDs gracefully', () => {
      const activityA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityA]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['NON_EXISTENT'],
        edges: [],
      })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(1)
      expect(activities[0].id).toBe('A')
    })

    it('handles invalid trigger indices', () => {
      const trigger = createManualTrigger('test-trigger-1', false)

      useWorkflowStore.setState({
        currentWorkflow: {
          ...makeWorkflow('Test'),
          triggers: [trigger],
        },
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: [],
        edges: [],
        triggerIndices: [99], // Out of bounds
      })

      const triggers = useWorkflowStore.getState().currentWorkflow?.triggers ?? []
      expect(triggers).toHaveLength(1)
    })
  })

  describe('State consistency', () => {
    it('maintains workflow structure integrity', () => {
      const activityA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const activityB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test Workflow', [activityA, activityB]),
        workflowVersion: 1,
        edges: [{ id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' }],
      })

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['B'],
        edges: [],
      })

      const workflow = useWorkflowStore.getState().currentWorkflow

      // Workflow structure should be intact
      expect(workflow).toBeDefined()
      expect(workflow?.name).toBe('Test Workflow')
      expect(workflow?.workflow).toBeDefined()
      expect(workflow?.workflow.activities).toBeDefined()
    })
  })
})
