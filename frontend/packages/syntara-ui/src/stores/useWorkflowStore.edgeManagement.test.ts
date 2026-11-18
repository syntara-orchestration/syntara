import { describe, expect, it, beforeEach } from 'vitest'

import type { EdgeConnection } from '../routes/builder/types/edge'

import {
  useWorkflowStore,
  createPythonScriptActivity,
  createConvergeActivity,
  createConditionActivity,
} from './useWorkflowStore'
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

describe('useWorkflowStore - Edge Management', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      currentWorkflow: null,
      workflowVersion: 0,
      edges: [],
    })
  })

  describe('setEdges', () => {
    it('sets edges correctly', () => {
      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges)

      expect(useWorkflowStore.getState().edges).toEqual(edges)
      expect(useWorkflowStore.getState().edges).toHaveLength(2)
    })

    it('replaces all edges atomically', () => {
      const edges1: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const edges2: EdgeConnection[] = [
        { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'D-E', source: 'D', target: 'E', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges1)
      expect(useWorkflowStore.getState().edges).toEqual(edges1)

      useWorkflowStore.getState().setEdges(edges2)
      expect(useWorkflowStore.getState().edges).toEqual(edges2)
      expect(useWorkflowStore.getState().edges).toHaveLength(2)
    })

    it('allows clearing all edges', () => {
      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges)
      expect(useWorkflowStore.getState().edges).toHaveLength(1)

      useWorkflowStore.getState().setEdges([])
      expect(useWorkflowStore.getState().edges).toEqual([])
    })

    it('preserves edge properties', () => {
      const edges: EdgeConnection[] = [
        {
          id: 'A-B',
          source: 'A',
          target: 'B',
          sourceHandle: 'true',
          targetHandle: 'target',
          type: 'custom',
          data: { customData: 'test' },
        } as EdgeConnection,
      ]

      useWorkflowStore.getState().setEdges(edges)

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges[0]).toEqual(edges[0])
    })
  })

  describe('Edge patterns with conditions', () => {
    it('handles condition node true/false handles', () => {
      const condition = createConditionActivity('A', 'Condition A', 'input.value > 10')
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'false', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [condition, taskB, taskC]),
        workflowVersion: 1,
        edges,
      })

      const storedEdges = useWorkflowStore.getState().edges

      expect(storedEdges).toHaveLength(2)
      expect(storedEdges.find((e) => e.sourceHandle === 'true')).toBeDefined()
      expect(storedEdges.find((e) => e.sourceHandle === 'false')).toBeDefined()
    })

    it('tracks edges from multiple condition nodes', () => {
      const conditionA = createConditionActivity('A', 'Condition A', 'input.a > 10')
      const conditionB = createConditionActivity('B', 'Condition B', 'input.b > 20')
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const taskD = createPythonScriptActivity({ id: 'D', name: 'Task D', code: 'print("D")' })

      const edges: EdgeConnection[] = [
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'false', targetHandle: 'target' },
        { id: 'B-D', source: 'B', target: 'D', sourceHandle: 'true', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [conditionA, conditionB, taskC, taskD]),
        workflowVersion: 1,
        edges,
      })

      expect(useWorkflowStore.getState().edges).toEqual(edges)
    })
  })

  describe('Edge patterns with converges', () => {
    it('tracks multiple edges to converge node', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const joinJ = createConvergeActivity('J', 'Converge J')

      const edges: EdgeConnection[] = [
        { id: 'A-J', source: 'A', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'C-J', source: 'C', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, taskC, joinJ]),
        workflowVersion: 1,
        edges,
      })

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(3)
      expect(storedEdges.filter((e) => e.target === 'J')).toHaveLength(3)
    })

    it('handles edges from converge to downstream activities', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const joinJ = createConvergeActivity('J', 'Converge J')
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      const edges: EdgeConnection[] = [
        { id: 'A-J', source: 'A', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'J-C', source: 'J', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, joinJ, taskC]),
        workflowVersion: 1,
        edges,
      })

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(3)

      // Verify edges to converge
      expect(storedEdges.filter((e) => e.target === 'J')).toHaveLength(2)

      // Verify edge from converge
      expect(storedEdges.find((e) => e.source === 'J')).toBeDefined()
    })

    it('preserves edges during converge sync', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const joinJ = createConvergeActivity('J', 'Converge J')

      const edges: EdgeConnection[] = [
        { id: 'A-J', source: 'A', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, joinJ]),
        workflowVersion: 1,
        edges,
      })

      // Sync join branches
      useWorkflowStore.getState().syncConvergeNodeBranches()

      // Edges should be preserved
      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toEqual(edges)
    })
  })

  describe('Edge removal scenarios', () => {
    it('removes specific edges while preserving others', () => {
      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges)

      // Remove middle edge
      const newEdges = edges.filter((e) => e.id !== 'B-C')
      useWorkflowStore.getState().setEdges(newEdges)

      expect(useWorkflowStore.getState().edges).toHaveLength(2)
      expect(useWorkflowStore.getState().edges.find((e) => e.id === 'A-B')).toBeDefined()
      expect(useWorkflowStore.getState().edges.find((e) => e.id === 'C-D')).toBeDefined()
      expect(useWorkflowStore.getState().edges.find((e) => e.id === 'B-C')).toBeUndefined()
    })

    it('handles removal of edges to deleted nodes', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, taskC]),
        workflowVersion: 1,
        edges,
      })

      // Remove B and its edges atomically
      const newEdges = edges.filter((e) => e.source !== 'B' && e.target !== 'B')

      useWorkflowStore.getState().batchRemoveNodesAndEdges({
        nodeIds: ['B'],
        edges: newEdges,
      })

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(0)
      expect(storedEdges.find((e) => e.source === 'B' || e.target === 'B')).toBeUndefined()
    })

    it('handles edge removal from condition branches', () => {
      const condition = createConditionActivity('A', 'Condition A', 'input.value > 10')
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'false', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [condition, taskB, taskC]),
        workflowVersion: 1,
        edges,
      })

      // Remove false branch edge
      const newEdges = edges.filter((e) => e.sourceHandle !== 'false')
      useWorkflowStore.getState().setEdges(newEdges)

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(1)
      expect(storedEdges[0].sourceHandle).toBe('true')
    })
  })

  describe('Complex edge scenarios', () => {
    it('handles diamond pattern (A->B,C; B,C->D)', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const taskD = createPythonScriptActivity({ id: 'D', name: 'Task D', code: 'print("D")' })

      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-D', source: 'B', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, taskC, taskD]),
        workflowVersion: 1,
        edges,
      })

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(4)

      // Verify branching from A
      expect(storedEdges.filter((e) => e.source === 'A')).toHaveLength(2)

      // Verify convergence to D
      expect(storedEdges.filter((e) => e.target === 'D')).toHaveLength(2)
    })

    it('handles multiple parallel paths with converges', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const convergeJ1 = createConvergeActivity('J1', 'Converge 1')
      const taskD = createPythonScriptActivity({ id: 'D', name: 'Task D', code: 'print("D")' })
      const taskE = createPythonScriptActivity({ id: 'E', name: 'Task E', code: 'print("E")' })
      const convergeJ2 = createConvergeActivity('J2', 'Converge 2')

      const edges: EdgeConnection[] = [
        // First parallel section
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-J1', source: 'B', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'C-J1', source: 'C', target: 'J1', sourceHandle: 'source', targetHandle: 'target' },
        // Second parallel section
        { id: 'J1-D', source: 'J1', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'J1-E', source: 'J1', target: 'E', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'D-J2', source: 'D', target: 'J2', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'E-J2', source: 'E', target: 'J2', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, taskC, convergeJ1, taskD, taskE, convergeJ2]),
        workflowVersion: 1,
        edges,
      })

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(8)

      // Verify first join
      expect(storedEdges.filter((e) => e.target === 'J1')).toHaveLength(2)

      // Verify second join
      expect(storedEdges.filter((e) => e.target === 'J2')).toHaveLength(2)

      // Verify connection between joins
      expect(storedEdges.filter((e) => e.source === 'J1')).toHaveLength(2)
    })

    it('handles condition with nested parallel paths', () => {
      const condition = createConditionActivity('A', 'Condition A', 'input.value > 10')
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const joinJ = createConvergeActivity('J', 'Converge J')
      const taskD = createPythonScriptActivity({ id: 'D', name: 'Task D', code: 'print("D")' })

      const edges: EdgeConnection[] = [
        // True branch splits into parallel
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'A-C', source: 'A', target: 'C', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'C-J', source: 'C', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        // False branch goes to D
        { id: 'A-D', source: 'A', target: 'D', sourceHandle: 'false', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [condition, taskB, taskC, joinJ, taskD]),
        workflowVersion: 1,
        edges,
      })

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(5)

      // Verify true branch edges
      expect(storedEdges.filter((e) => e.sourceHandle === 'true')).toHaveLength(2)

      // Verify false branch edge
      expect(storedEdges.filter((e) => e.sourceHandle === 'false')).toHaveLength(1)

      // Verify join edges
      expect(storedEdges.filter((e) => e.target === 'J')).toHaveLength(2)
    })
  })

  describe('Edge validation and integrity', () => {
    it('preserves edge IDs', () => {
      const edges: EdgeConnection[] = [
        { id: 'custom-id-1', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'custom-id-2', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges)

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges[0].id).toBe('custom-id-1')
      expect(storedEdges[1].id).toBe('custom-id-2')
    })

    it('handles edges with same source and target but different handles', () => {
      const edges: EdgeConnection[] = [
        { id: 'A-B-true', source: 'A', target: 'B', sourceHandle: 'true', targetHandle: 'target' },
        { id: 'A-B-false', source: 'A', target: 'B', sourceHandle: 'false', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges)

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges).toHaveLength(2)
      expect(storedEdges.every((e) => e.source === 'A' && e.target === 'B')).toBe(true)
    })

    it('maintains edge order', () => {
      const edges: EdgeConnection[] = [
        { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges)

      const storedEdges = useWorkflowStore.getState().edges
      expect(storedEdges.map((e) => e.id)).toEqual(['C-D', 'A-B', 'B-C'])
    })
  })

  describe('Edge state consistency', () => {
    it('maintains edge state across activity operations', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, taskC]),
        workflowVersion: 1,
        edges,
      })

      // Update activity B
      useWorkflowStore.getState().updateActivity('B', { name: 'Updated Task B' })

      // Edges should remain unchanged
      expect(useWorkflowStore.getState().edges).toEqual(edges)
    })

    it('maintains edge state during activity reordering', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })

      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-C', source: 'B', target: 'C', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskC, taskA, taskB]),
        workflowVersion: 1,
        edges,
      })

      // Reorder activities
      useWorkflowStore.getState().reorderActivitiesFromEdges()

      // Edges should remain unchanged
      expect(useWorkflowStore.getState().edges).toEqual(edges)
    })

    it('maintains edge state during join synchronization', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const joinJ = createConvergeActivity('J', 'Converge J')

      const edges: EdgeConnection[] = [
        { id: 'A-J', source: 'A', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, joinJ]),
        workflowVersion: 1,
        edges,
      })

      // Sync join branches
      useWorkflowStore.getState().syncConvergeNodeBranches()

      // Edges should remain unchanged
      expect(useWorkflowStore.getState().edges).toEqual(edges)
    })

    it('sets converge parameters.branches to individual activity IDs when branches converge', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const joinJ = createConvergeActivity('J', 'Converge J')

      // Edges from activities to converge
      const edges: EdgeConnection[] = [
        { id: 'A-J', source: 'A', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, joinJ]),
        workflowVersion: 1,
        edges,
      })

      // Sync converge node branches
      useWorkflowStore.getState().syncConvergeNodeBranches()

      // Get the updated converge activity
      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities
      const converge = activities?.find((a) => a.id === 'J')

      // v2: converge.parameters.branches should contain individual activity IDs
      expect(converge?.parameters.branches).toContain('A')
      expect(converge?.parameters.branches).toContain('B')
      expect(converge?.parameters.branches).toHaveLength(2)
    })

    it('handles partial convergence', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const joinJ = createConvergeActivity('J', 'Converge J')

      // Only A converges to J (B doesn't)
      const edges: EdgeConnection[] = [
        { id: 'A-J', source: 'A', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, joinJ]),
        workflowVersion: 1,
        edges,
      })

      // Sync converge node branches
      useWorkflowStore.getState().syncConvergeNodeBranches()

      // Get the updated converge activity
      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities
      const converge = activities?.find((a) => a.id === 'J')

      expect(converge?.parameters.branches).toEqual(['A'])
    })

    it('handles mixed convergence from multiple activities', () => {
      const taskA = createPythonScriptActivity({ id: 'A', name: 'Task A', code: 'print("A")' })
      const taskB = createPythonScriptActivity({ id: 'B', name: 'Task B', code: 'print("B")' })
      const taskC = createPythonScriptActivity({ id: 'C', name: 'Task C', code: 'print("C")' })
      const joinJ = createConvergeActivity('J', 'Converge J')

      // All three converge to J
      const edges: EdgeConnection[] = [
        { id: 'A-J', source: 'A', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'B-J', source: 'B', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'C-J', source: 'C', target: 'J', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [taskA, taskB, taskC, joinJ]),
        workflowVersion: 1,
        edges,
      })

      // Sync converge node branches
      useWorkflowStore.getState().syncConvergeNodeBranches()

      // Get the updated converge activity
      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities
      const converge = activities?.find((a) => a.id === 'J')

      // Should reference ALL individual activity IDs
      expect(converge?.parameters.branches).toContain('A')
      expect(converge?.parameters.branches).toContain('B')
      expect(converge?.parameters.branches).toContain('C')
      expect(converge?.parameters.branches).toHaveLength(3)
    })
  })
})
