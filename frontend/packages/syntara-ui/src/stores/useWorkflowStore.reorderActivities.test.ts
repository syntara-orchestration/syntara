import { describe, expect, it, beforeEach } from 'vitest'

import { useWorkflowStore, createScriptActivity } from './useWorkflowStore'
import type { Activity, WorkflowDefinition } from './workflowStoreTypes'

// Helper to create a v2 WorkflowDefinition for tests
function makeWorkflow(name: string, activities: Activity[] = []): WorkflowDefinition {
  return {
    schema_version: '2.0.0',
    name,
    description: '',
    triggers: [],
    workflow: { activities },
  }
}

describe('useWorkflowStore - reorderActivitiesFromEdges', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      currentWorkflow: null,
      workflowVersion: 0,
      edges: [],
    })
  })

  describe('Topological sorting', () => {
    it('reorders activities based on edges (simple chain)', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })

      // Activities in wrong order
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityC, activityA, activityB]),
        workflowVersion: 1,
        edges: [
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities.map((a) => a.id)).toEqual(['A', 'B', 'C'])
    })

    it('handles branching paths', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })
      const activityD = createScriptActivity({ id: 'D', name: 'Task D', language: 'python', code: 'print("D")' })

      // A -> B -> D
      // A -> C -> D
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityD, activityC, activityB, activityA]),
        workflowVersion: 1,
        edges: [
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'B-D', source: 'B', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      const ids = activities.map((a) => a.id)

      // A should be first, D should be last
      expect(ids[0]).toBe('A')
      expect(ids[3]).toBe('D')
      // B and C should be in the middle (order between them is deterministic due to sort)
      expect(ids.slice(1, 3).sort()).toEqual(['B', 'C'])
    })

    it('handles complex DAG', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })
      const activityD = createScriptActivity({ id: 'D', name: 'Task D', language: 'python', code: 'print("D")' })
      const activityE = createScriptActivity({ id: 'E', name: 'Task E', language: 'python', code: 'print("E")' })

      // A -> B -> D -> E
      //  \\-> C -/
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityE, activityD, activityC, activityB, activityA]),
        workflowVersion: 1,
        edges: [
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'B-D', source: 'B', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'D-E', source: 'D', target: 'E', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      const ids = activities.map((a) => a.id)

      // Verify topological order
      expect(ids.indexOf('A')).toBeLessThan(ids.indexOf('B'))
      expect(ids.indexOf('A')).toBeLessThan(ids.indexOf('C'))
      expect(ids.indexOf('B')).toBeLessThan(ids.indexOf('D'))
      expect(ids.indexOf('C')).toBeLessThan(ids.indexOf('D'))
      expect(ids.indexOf('D')).toBeLessThan(ids.indexOf('E'))
    })
  })

  describe('Handling flat activities', () => {
    it('reorders all activities in flat list', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const conditionActivity: Activity = {
        type: 'condition',
        id: 'COND',
        name: 'Condition',
        parameters: { condition: 'input.value > 10' },
      }

      // C -> COND
      // A -> C
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [conditionActivity, activityB, activityA]),
        workflowVersion: 1,
        edges: [
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'B-COND', source: 'B', target: 'COND', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities.map((a) => a.id)).toEqual(['A', 'B', 'COND'])
    })
  })

  describe('Preserving unconnected activities', () => {
    it('keeps activities without edges at the end', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })
      const activityOrphan = createScriptActivity({
        id: 'ORPHAN',
        name: 'Orphan',
        language: 'python',
        code: 'print("orphan")',
      })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityOrphan, activityC, activityA, activityB]),
        workflowVersion: 1,
        edges: [
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      const ids = activities.map((a) => a.id)

      // Connected activities should be ordered
      expect(ids.slice(0, 3)).toEqual(['A', 'B', 'C'])
      // Orphan should be preserved
      expect(ids).toContain('ORPHAN')
      expect(activities).toHaveLength(4)
    })

    it('preserves all activities even with no edges', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityB, activityA]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(2)
      expect(activities.map((a) => a.id).sort()).toEqual(['A', 'B'])
    })
  })

  describe('Deterministic ordering', () => {
    it('produces consistent order for nodes at same level', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })

      // B and C have no ordering constraint (both depend on nothing)
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityC, activityA, activityB]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const run1 = useWorkflowStore.getState().currentWorkflow?.workflow.activities.map((a) => a.id) ?? []

      // Reset and run again
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityB, activityC, activityA]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const run2 = useWorkflowStore.getState().currentWorkflow?.workflow.activities.map((a) => a.id) ?? []

      // The input order changes, so a stable reorder must produce the same explicit order.
      expect(run1).toEqual(['A', 'B', 'C'])
      expect(run2).toEqual(['A', 'B', 'C'])
    })
  })

  describe('Edge cases', () => {
    it('does nothing when no workflow is set', () => {
      useWorkflowStore.setState({ currentWorkflow: null })

      expect(() => useWorkflowStore.getState().reorderActivitiesFromEdges()).not.toThrow()
      expect(useWorkflowStore.getState().currentWorkflow).toBeNull()
    })

    it('handles empty activities array', () => {
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test'),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(0)
    })

    it('handles self-referential edges (should be filtered)', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityB, activityA]),
        workflowVersion: 1,
        edges: [
          { id: 'A-A', source: 'A', target: 'A', sourceHandle: 'source', targetHandle: 'target' }, // Self-loop
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities.map((a) => a.id)).toEqual(['A', 'B'])
    })

    it('preserves all activities even with duplicate edges', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityB, activityA]),
        workflowVersion: 1,
        edges: [
          { id: 'A-B-1', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'A-B-2', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(2)
      expect(activities.map((a) => a.id)).toEqual(['A', 'B'])
    })
  })

  describe('Safety check', () => {
    it('never removes activities during reordering', () => {
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activityA, activityB, activityC]),
        workflowVersion: 1,
        edges: [
          // Only A->B edge, C is disconnected
          { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []

      // All three activities must be preserved
      expect(activities).toHaveLength(3)
      expect(activities.map((a) => a.id).sort()).toEqual(['A', 'B', 'C'])
    })

    it('reorders activities with loop nodes using done handle', () => {
      const startActivity = createScriptActivity({
        id: 'START',
        name: 'Start',
        language: 'python',
        code: 'print("start")',
      })
      const activityA = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const loopBodyC = createScriptActivity({ id: 'C', name: 'Loop Body C', language: 'python', code: 'print("C")' })
      const loopB: Activity = {
        type: 'loop',
        id: 'B',
        name: 'Loop B',
        parameters: {
          type: 'for_each',
          items: 'input.items',
        },
      }

      // Initial order: START->A->B with C inside loop body
      // Change to: START->B->A (reconnect edges)
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [startActivity, activityA, loopB, loopBodyC]),
        workflowVersion: 1,
        edges: [
          // NEW edge configuration: START->B->A
          { id: 'START-B', source: 'START', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'B-A', source: 'B', target: 'A', sourceHandle: 'done', targetHandle: 'target' },
          // Loop internal edges (should be ignored for ordering)
          { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'loop', targetHandle: 'target' },
          { id: 'C-B', source: 'C', target: 'B', sourceHandle: 'source', targetHandle: 'end' },
        ],
      })

      useWorkflowStore.getState().reorderActivitiesFromEdges()

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []

      // All activities should be preserved
      expect(activities).toHaveLength(4)
      const topLevelIds = activities.map((a) => a.id)
      const startIndex = topLevelIds.indexOf('START')
      const bIndex = topLevelIds.indexOf('B')

      // Verify correct ordering: START < B
      expect(startIndex).toBeLessThan(bIndex)
    })
  })
})
