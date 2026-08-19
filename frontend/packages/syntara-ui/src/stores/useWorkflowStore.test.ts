import { describe, expect, it, beforeEach } from 'vitest'

import type { EdgeConnection } from '../routes/builder/types/edge'

import {
  useWorkflowStore,
  createManualTrigger,
  createConvergeActivity,
  createScriptActivity,
  createGenericActivity,
} from './useWorkflowStore'
import { wrappedUndo, wrappedRedo } from './workflowStoreSelectors'
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

describe('useWorkflowStore', () => {
  beforeEach(() => {
    // Reset store before each test
    useWorkflowStore.setState({
      currentWorkflow: null,
      workflowVersion: 0,
      edges: [],
    })
  })

  describe('setWorkflow', () => {
    it('sets workflow and increments version', () => {
      const workflow = makeWorkflow('Test Workflow')

      expect(useWorkflowStore.getState().workflowVersion).toBe(0)

      useWorkflowStore.getState().setWorkflow(workflow)

      const state = useWorkflowStore.getState()
      expect(state.currentWorkflow).toEqual(workflow)
      expect(state.workflowVersion).toBe(1)
    })

    it('increments version on each call', () => {
      const workflow = makeWorkflow('Test Workflow')

      useWorkflowStore.getState().setWorkflow(workflow)
      expect(useWorkflowStore.getState().workflowVersion).toBe(1)

      useWorkflowStore.getState().setWorkflow(workflow)
      expect(useWorkflowStore.getState().workflowVersion).toBe(2)

      useWorkflowStore.getState().setWorkflow(workflow)
      expect(useWorkflowStore.getState().workflowVersion).toBe(3)
    })

    it('allows setting workflow to null', () => {
      const workflow = makeWorkflow('Test Workflow')

      useWorkflowStore.getState().setWorkflow(workflow)
      expect(useWorkflowStore.getState().currentWorkflow).not.toBeNull()

      useWorkflowStore.getState().setWorkflow(null)
      expect(useWorkflowStore.getState().currentWorkflow).toBeNull()
      expect(useWorkflowStore.getState().workflowVersion).toBe(2)
    })
  })

  describe('setEdges', () => {
    it('sets edges', () => {
      const edges: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges)

      expect(useWorkflowStore.getState().edges).toEqual(edges)
    })

    it('replaces existing edges', () => {
      const edges1: EdgeConnection[] = [
        { id: 'A-B', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const edges2: EdgeConnection[] = [
        { id: 'C-D', source: 'C', target: 'D', sourceHandle: 'source', targetHandle: 'target' },
      ]

      useWorkflowStore.getState().setEdges(edges1)
      expect(useWorkflowStore.getState().edges).toEqual(edges1)

      useWorkflowStore.getState().setEdges(edges2)
      expect(useWorkflowStore.getState().edges).toEqual(edges2)
    })
  })

  describe('Trigger management', () => {
    beforeEach(() => {
      useWorkflowStore.getState().setWorkflow(makeWorkflow('Test Workflow'))
    })

    describe('addTrigger', () => {
      it('adds trigger to empty array', () => {
        const trigger = createManualTrigger('test-trigger-1', false)

        useWorkflowStore.getState().addTrigger(trigger)

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.triggers).toHaveLength(1)
        expect(state.currentWorkflow?.triggers?.[0]).toEqual(trigger)
      })

      it('adds multiple triggers', () => {
        const trigger1 = createManualTrigger('test-trigger-1', false)
        const trigger2 = createManualTrigger('test-trigger-2', true)

        useWorkflowStore.getState().addTrigger(trigger1)
        useWorkflowStore.getState().addTrigger(trigger2)

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.triggers).toHaveLength(2)
        expect(state.currentWorkflow?.triggers).toEqual([trigger1, trigger2])
      })

      it('does nothing when no workflow is set', () => {
        useWorkflowStore.setState({ currentWorkflow: null })

        const trigger = createManualTrigger('test-trigger-1', false)
        useWorkflowStore.getState().addTrigger(trigger)

        expect(useWorkflowStore.getState().currentWorkflow).toBeNull()
      })
    })

    describe('removeTrigger', () => {
      it('removes trigger by index', () => {
        const trigger1 = createManualTrigger('test-trigger-1', false)
        const trigger2 = createManualTrigger('test-trigger-2', true)

        useWorkflowStore.getState().addTrigger(trigger1)
        useWorkflowStore.getState().addTrigger(trigger2)
        useWorkflowStore.getState().removeTrigger(0)

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.triggers).toHaveLength(1)
        expect(state.currentWorkflow?.triggers?.[0]).toEqual(trigger2)
      })

      it('does nothing when no triggers exist', () => {
        useWorkflowStore.getState().removeTrigger(0)

        expect(useWorkflowStore.getState().currentWorkflow?.triggers).toEqual([])
      })

      it('removes edges connected to deleted trigger', () => {
        const workflow = makeWorkflow('Test', [
          createScriptActivity({ id: 'activity-1', name: 'Script', language: 'python', code: '' }),
        ])
        const trigger1 = createManualTrigger('test-trigger-1', false)
        const trigger2 = createManualTrigger('test-trigger-2', true)

        useWorkflowStore.setState({ currentWorkflow: workflow })
        useWorkflowStore.getState().addTrigger(trigger1)
        useWorkflowStore.getState().addTrigger(trigger2)

        // Create edges using real trigger IDs (how they are in the actual app)
        const edges: EdgeConnection[] = [
          { id: 'test-trigger-1-activity-1', source: 'test-trigger-1', target: 'activity-1', sourceHandle: 'source' },
          { id: 'test-trigger-2-activity-1', source: 'test-trigger-2', target: 'activity-1', sourceHandle: 'source' },
        ]
        useWorkflowStore.setState({ edges })

        // Remove trigger-0 (test-trigger-1)
        useWorkflowStore.getState().removeTrigger(0)

        const state = useWorkflowStore.getState()
        // Edge from deleted trigger test-trigger-1 should be removed
        expect(state.edges).toHaveLength(1)
        // Remaining edge should still reference test-trigger-2 (real ID doesn't change)
        expect(state.edges[0]).toEqual({
          id: 'test-trigger-2-activity-1',
          source: 'test-trigger-2',
          target: 'activity-1',
          sourceHandle: 'source',
        })
      })

      it('removes edge when trigger is deleted from middle', () => {
        const workflow = makeWorkflow('Test', [
          createScriptActivity({ id: 'activity-1', name: 'Script', language: 'python', code: '' }),
        ])
        const trigger1 = createManualTrigger('test-trigger-1', false)
        const trigger2 = createManualTrigger('test-trigger-2', true)
        const trigger3 = createManualTrigger('test-trigger-3', false)

        useWorkflowStore.setState({ currentWorkflow: workflow })
        useWorkflowStore.getState().addTrigger(trigger1)
        useWorkflowStore.getState().addTrigger(trigger2)
        useWorkflowStore.getState().addTrigger(trigger3)

        // Create edges using real trigger IDs (how they are in the actual app)
        const edges: EdgeConnection[] = [
          { id: 'test-trigger-1-activity-1', source: 'test-trigger-1', target: 'activity-1', sourceHandle: 'source' },
          { id: 'test-trigger-2-activity-1', source: 'test-trigger-2', target: 'activity-1', sourceHandle: 'source' },
          { id: 'test-trigger-3-activity-1', source: 'test-trigger-3', target: 'activity-1', sourceHandle: 'source' },
        ]
        useWorkflowStore.setState({ edges })

        // Remove trigger-1 (test-trigger-2, middle one)
        useWorkflowStore.getState().removeTrigger(1)

        const state = useWorkflowStore.getState()
        // Edge from deleted trigger test-trigger-2 should be removed
        // Other edges remain unchanged (real IDs don't shift)
        expect(state.edges).toHaveLength(2)
        expect(state.edges).toContainEqual({
          id: 'test-trigger-1-activity-1',
          source: 'test-trigger-1',
          target: 'activity-1',
          sourceHandle: 'source',
        })
        expect(state.edges).toContainEqual({
          id: 'test-trigger-3-activity-1',
          source: 'test-trigger-3',
          target: 'activity-1',
          sourceHandle: 'source',
        })
      })

      it('handles edges with trigger as target', () => {
        const workflow = makeWorkflow('Test', [
          createScriptActivity({ id: 'activity-1', name: 'Script', language: 'python', code: '' }),
        ])
        const trigger1 = createManualTrigger('test-trigger-1', false)
        const trigger2 = createManualTrigger('test-trigger-2', true)

        useWorkflowStore.setState({ currentWorkflow: workflow })
        useWorkflowStore.getState().addTrigger(trigger1)
        useWorkflowStore.getState().addTrigger(trigger2)

        // Create edges using real trigger IDs (how they are in the actual app)
        const edges: EdgeConnection[] = [
          { id: 'activity-1-test-trigger-1', source: 'activity-1', target: 'test-trigger-1', sourceHandle: 'source' },
          { id: 'activity-1-test-trigger-2', source: 'activity-1', target: 'test-trigger-2', sourceHandle: 'source' },
        ]
        useWorkflowStore.setState({ edges })

        // Remove trigger-0 (test-trigger-1)
        useWorkflowStore.getState().removeTrigger(0)

        const state = useWorkflowStore.getState()
        expect(state.edges).toHaveLength(1)
        // Remaining edge still references test-trigger-2 (real ID doesn't change)
        expect(state.edges[0]).toEqual({
          id: 'activity-1-test-trigger-2',
          source: 'activity-1',
          target: 'test-trigger-2',
          sourceHandle: 'source',
        })
      })
    })

    describe('updateTrigger', () => {
      it('updates trigger at index', () => {
        const trigger1 = createManualTrigger('test-trigger-1', false)
        const trigger2 = createManualTrigger('test-trigger-2', true)

        useWorkflowStore.getState().addTrigger(trigger1)
        useWorkflowStore.getState().updateTrigger(0, trigger2)

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.triggers?.[0]).toEqual(trigger2)
      })
    })
  })

  describe('Activity management', () => {
    beforeEach(() => {
      useWorkflowStore.getState().setWorkflow(makeWorkflow('Test Workflow'))
    })

    describe('addActivity', () => {
      it('adds activity to empty array', () => {
        const activity = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })

        useWorkflowStore.getState().addActivity(activity)

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.workflow.activities).toHaveLength(1)
        expect(state.currentWorkflow?.workflow.activities[0]).toEqual(activity)
      })

      it('adds multiple activities', () => {
        const activity1 = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
        const activity2 = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })

        useWorkflowStore.getState().addActivity(activity1)
        useWorkflowStore.getState().addActivity(activity2)

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.workflow.activities).toHaveLength(2)
        expect(state.currentWorkflow?.workflow.activities).toEqual([activity1, activity2])
      })
    })

    describe('removeActivity', () => {
      it('removes activity from flat list', () => {
        const activity1 = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
        const activity2 = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })

        useWorkflowStore.getState().addActivity(activity1)
        useWorkflowStore.getState().addActivity(activity2)
        useWorkflowStore.getState().removeActivity('A')

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.workflow.activities).toHaveLength(1)
        expect(state.currentWorkflow?.workflow.activities[0].id).toBe('B')
      })

      it('removes converge activity from flat list', () => {
        const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
        const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })
        const convergeActivity = createConvergeActivity('J', 'Converge J')

        useWorkflowStore.setState({
          currentWorkflow: makeWorkflow('Test', [activityB, activityC, convergeActivity]),
          workflowVersion: 1,
          edges: [],
        })

        useWorkflowStore.getState().removeActivity('J')

        const state = useWorkflowStore.getState()
        const activities = state.currentWorkflow?.workflow.activities ?? []

        // Join should be removed
        expect(activities.find((a) => a.id === 'J')).toBeUndefined()
        // Other activities should remain
        expect(activities.find((a) => a.id === 'B')).toBeDefined()
        expect(activities.find((a) => a.id === 'C')).toBeDefined()
      })

      it('removes condition activity from flat list', () => {
        const conditionActivity: Activity = {
          type: 'condition',
          id: 'A',
          name: 'Condition A',
          parameters: { condition: 'input.value > 10' },
        }
        const activityB = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
        const activityC = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })

        useWorkflowStore.setState({
          currentWorkflow: makeWorkflow('Test', [conditionActivity, activityB, activityC]),
          workflowVersion: 1,
          edges: [],
        })

        useWorkflowStore.getState().removeActivity('A')

        const state = useWorkflowStore.getState()
        const activities = state.currentWorkflow?.workflow.activities ?? []

        expect(activities.find((a) => a.id === 'A')).toBeUndefined()
        expect(activities).toHaveLength(2)
      })
    })

    describe('updateActivity', () => {
      it('updates activity in flat list', () => {
        const activity = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })

        useWorkflowStore.getState().addActivity(activity)
        useWorkflowStore.getState().updateActivity('A', { name: 'Updated Task A' })

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.workflow.activities[0].name).toBe('Updated Task A')
      })

      it('updates condition activity in flat list', () => {
        const conditionActivity: Activity = {
          type: 'condition',
          id: 'A',
          name: 'Condition A',
          parameters: { condition: 'input.value > 10' },
        }

        useWorkflowStore.setState({
          currentWorkflow: makeWorkflow('Test', [conditionActivity]),
          workflowVersion: 1,
          edges: [],
        })

        useWorkflowStore.getState().updateActivity('A', { name: 'Updated Condition' })

        const state = useWorkflowStore.getState()
        expect(state.currentWorkflow?.workflow.activities[0].name).toBe('Updated Condition')
      })
    })
  })

  describe('moveActivityBefore', () => {
    it('moves activity before target', () => {
      const activity1 = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activity2 = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activity3 = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activity1, activity2, activity3]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().moveActivityBefore('C', 'A')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities.map((a) => a.id)).toEqual(['C', 'A', 'B'])
    })

    it('does nothing if activity is already before target', () => {
      const activity1 = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activity2 = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activity1, activity2]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().moveActivityBefore('A', 'B')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities.map((a) => a.id)).toEqual(['A', 'B'])
    })
  })

  describe('moveActivityAfter', () => {
    it('moves activity after target', () => {
      const activity1 = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activity2 = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })
      const activity3 = createScriptActivity({ id: 'C', name: 'Task C', language: 'python', code: 'print("C")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activity1, activity2, activity3]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().moveActivityAfter('A', 'C')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities.map((a) => a.id)).toEqual(['B', 'C', 'A'])
    })

    it('does nothing if activity is already after target', () => {
      const activity1 = createScriptActivity({ id: 'A', name: 'Task A', language: 'python', code: 'print("A")' })
      const activity2 = createScriptActivity({ id: 'B', name: 'Task B', language: 'python', code: 'print("B")' })

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow('Test', [activity1, activity2]),
        workflowVersion: 1,
        edges: [],
      })

      useWorkflowStore.getState().moveActivityAfter('B', 'A')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities.map((a) => a.id)).toEqual(['A', 'B'])
    })
  })

  describe('createGenericActivity', () => {
    it('creates a minimal generic placeholder node', () => {
      const activity = createGenericActivity('generic-1', 'Placeholder')

      expect(activity).toMatchObject({
        type: 'generic',
        id: 'generic-1',
        name: 'Placeholder',
        parameters: {},
        metadata: {
          __isGeneric: true,
        },
      })
    })

    it('creates generic node with metadata', () => {
      const activity = createGenericActivity('generic-1', 'Test')

      expect((activity.metadata as { __isGeneric?: boolean })?.__isGeneric).toBe(true)
    })

    it('uses default name when not provided', () => {
      const activity = createGenericActivity('generic-1')

      expect(activity.name).toBe('New Step')
    })

    it('includes custom message in metadata when provided', () => {
      const activity = createGenericActivity('generic-1', 'Test', 'Custom message here')

      expect(activity.metadata as Record<string, unknown>).toMatchObject({
        __isGeneric: true,
        __customMessage: 'Custom message here',
      })
    })

    it('does not include custom message when not provided', () => {
      const activity = createGenericActivity('generic-1', 'Test')

      expect(activity.metadata).toEqual({
        __isGeneric: true,
      })
    })

    it('always sets __isGeneric to true', () => {
      const activity = createGenericActivity('generic-1', 'Test')

      expect(activity.metadata).toHaveProperty('__isGeneric', true)
    })
  })

  describe('duplicateActivity', () => {
    const baseWorkflow = makeWorkflow('Test')

    beforeEach(() => {
      useWorkflowStore.getState().setWorkflow(baseWorkflow)
    })

    it('returns null when the workflow is not loaded', () => {
      useWorkflowStore.setState({ currentWorkflow: null })
      const result = useWorkflowStore.getState().duplicateActivity('nonexistent')
      expect(result).toBeNull()
    })

    it('returns null when the activity is not found', () => {
      const result = useWorkflowStore.getState().duplicateActivity('nonexistent')
      expect(result).toBeNull()
    })

    it('appends a clone with a new ID and marks dirty', () => {
      const original = createScriptActivity({ id: 'act-1', name: 'Script', language: 'python', code: 'print(1)' })
      useWorkflowStore.getState().addActivity(original)

      const newId = useWorkflowStore.getState().duplicateActivity('act-1')

      expect(newId).not.toBeNull()
      expect(newId).not.toBe('act-1')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(2)
      expect(activities[1].id).toBe(newId)
      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    it('names the clone "Copy of <original name>"', () => {
      const original = createScriptActivity({ id: 'act-1', name: 'My Script', language: 'python', code: 'print(1)' })
      useWorkflowStore.getState().addActivity(original)

      useWorkflowStore.getState().duplicateActivity('act-1')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities[1].name).toBe('Copy of My Script')
    })

    it('generates a unique name when "Copy of…" already exists', () => {
      const original = createScriptActivity({ id: 'act-1', name: 'Script', language: 'python', code: 'print(1)' })
      const copy1 = createScriptActivity({ id: 'act-2', name: 'Copy of Script', language: 'python', code: 'print(1)' })
      useWorkflowStore.getState().addActivity(original)
      useWorkflowStore.getState().addActivity(copy1)

      useWorkflowStore.getState().duplicateActivity('act-1')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities[2].name).toBe('Copy of Script2')
    })

    it('preserves the original activity type and config', () => {
      const original = createScriptActivity({ id: 'act-1', name: 'Script', language: 'python', code: 'print("hello")' })
      useWorkflowStore.getState().addActivity(original)

      const newId = useWorkflowStore.getState().duplicateActivity('act-1')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      const clone = activities.find((a) => a.id === newId)
      expect(clone?.type).toBe('script')
      expect(clone?.parameters).toEqual(original.parameters)
    })

    it('does not share object references between original and clone', () => {
      const original = createScriptActivity({ id: 'act-1', name: 'Script', language: 'python', code: 'print(1)' })
      useWorkflowStore.getState().addActivity(original)

      const newId = useWorkflowStore.getState().duplicateActivity('act-1')

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      const clone = activities.find((a) => a.id === newId)
      expect(clone).not.toBe(original)
    })
  })

  describe('replaceActivity', () => {
    const baseWorkflow = makeWorkflow('Test')

    beforeEach(() => {
      useWorkflowStore.getState().setWorkflow(baseWorkflow)
    })

    it('replaces the activity in place and marks dirty', () => {
      const original = createScriptActivity({ id: 'act-1', name: 'Script', language: 'python', code: 'print(1)' })
      const replacement = createScriptActivity({ id: 'tmp-id', name: 'REST API', language: 'python', code: 'print(2)' })
      useWorkflowStore.getState().addActivity(original)

      useWorkflowStore.getState().replaceActivity('act-1', { ...replacement, id: 'act-1' })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      expect(activities).toHaveLength(1)
      expect(activities[0].id).toBe('act-1')
      expect(activities[0].name).toBe('REST API')
      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    it('does not carry over type-specific fields from the old activity', () => {
      const conditionActivity: Activity = {
        type: 'condition',
        id: 'cond-1',
        name: 'My Condition',
        parameters: { condition: 'some.expr' },
      }
      const scriptActivity = createScriptActivity({
        id: 'tmp-id',
        name: 'Script Node',
        language: 'python',
        code: 'print(1)',
      })
      useWorkflowStore.getState().addActivity(conditionActivity)

      useWorkflowStore.getState().replaceActivity('cond-1', { ...scriptActivity, id: 'cond-1' })

      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []
      const replaced = activities[0] as Record<string, unknown>
      expect(replaced.type).toBe('script')
      // v2: condition expression is inside config, so replaced activity should have script config
      expect((replaced.parameters as Record<string, unknown>).condition).toBeUndefined()
    })

    it('preserves list order when replacing a non-first activity', () => {
      const act1 = createScriptActivity({ id: 'act-1', name: 'First', language: 'python', code: '' })
      const act2 = createScriptActivity({ id: 'act-2', name: 'Second', language: 'python', code: '' })
      const act3 = createScriptActivity({ id: 'act-3', name: 'Third', language: 'python', code: '' })
      useWorkflowStore.getState().addActivity(act1)
      useWorkflowStore.getState().addActivity(act2)
      useWorkflowStore.getState().addActivity(act3)

      const replacement = createScriptActivity({ id: 'tmp', name: 'Replaced', language: 'python', code: '' })
      useWorkflowStore.getState().replaceActivity('act-2', { ...replacement, id: 'act-2' })

      const ids = (useWorkflowStore.getState().currentWorkflow?.workflow.activities ?? []).map((a) => a.id)
      expect(ids).toEqual(['act-1', 'act-2', 'act-3'])
    })

    it('does nothing when the workflow is not loaded', () => {
      useWorkflowStore.setState({ currentWorkflow: null })
      const scriptActivity = createScriptActivity({ id: 'tmp', name: 'Script', language: 'python', code: '' })
      useWorkflowStore.getState().replaceActivity('any-id', scriptActivity)
      expect(useWorkflowStore.getState().currentWorkflow).toBeNull()
    })

    it('removes type-specific outgoing edges when replacing a condition node with a script node', () => {
      const conditionActivity: Activity = {
        type: 'condition',
        id: 'cond-1',
        name: 'My Condition',
        parameters: { condition: 'some.expr' },
      }
      useWorkflowStore.getState().addActivity(conditionActivity)
      useWorkflowStore.setState({
        edges: [
          { id: 'e-true', source: 'cond-1', target: 'node-a', sourceHandle: 'true', targetHandle: 'target' },
          { id: 'e-false', source: 'cond-1', target: 'node-b', sourceHandle: 'false', targetHandle: 'target' },
          { id: 'e-in', source: 'prev-node', target: 'cond-1', sourceHandle: 'source', targetHandle: 'target' },
        ] as EdgeConnection[],
      })

      const scriptActivity = createScriptActivity({
        id: 'tmp',
        name: 'Script Node',
        language: 'python',
        code: 'print(1)',
      })
      useWorkflowStore.getState().replaceActivity('cond-1', { ...scriptActivity, id: 'cond-1' })

      const edges = useWorkflowStore.getState().edges
      expect(edges.map((e) => e.id)).toEqual(['e-in'])
    })

    it('removes approval-specific outgoing edges when replacing an approval node with a script node', () => {
      const approvalActivity: Activity = {
        type: 'approval',
        id: 'appr-1',
        name: 'My Approval',
        parameters: {},
      }
      useWorkflowStore.getState().addActivity(approvalActivity)
      useWorkflowStore.setState({
        edges: [
          { id: 'e-ok', source: 'appr-1', target: 'node-a', sourceHandle: 'approved', targetHandle: 'target' },
          { id: 'e-no', source: 'appr-1', target: 'node-b', sourceHandle: 'rejected', targetHandle: 'target' },
          { id: 'e-in', source: 'prev-node', target: 'appr-1', sourceHandle: 'source', targetHandle: 'target' },
        ] as EdgeConnection[],
      })

      const scriptActivity = createScriptActivity({
        id: 'tmp',
        name: 'Script Node',
        language: 'python',
        code: 'print(1)',
      })
      useWorkflowStore.getState().replaceActivity('appr-1', { ...scriptActivity, id: 'appr-1' })

      const edges = useWorkflowStore.getState().edges
      expect(edges.map((e) => e.id)).toEqual(['e-in'])
    })

    it('removes loop-specific outgoing edges when replacing a loop node with a script node', () => {
      const loopActivity: Activity = {
        type: 'loop',
        id: 'loop-1',
        name: 'My Loop',
        parameters: { type: 'for_each', items: '{{ items }}' },
      }
      useWorkflowStore.getState().addActivity(loopActivity)
      useWorkflowStore.setState({
        edges: [
          { id: 'e-loop', source: 'loop-1', target: 'node-a', sourceHandle: 'loop', targetHandle: 'target' },
          { id: 'e-done', source: 'loop-1', target: 'node-b', sourceHandle: 'done', targetHandle: 'target' },
          { id: 'e-in', source: 'prev-node', target: 'loop-1', sourceHandle: 'source', targetHandle: 'target' },
        ] as EdgeConnection[],
      })

      const scriptActivity = createScriptActivity({
        id: 'tmp',
        name: 'Script Node',
        language: 'python',
        code: 'print(1)',
      })
      useWorkflowStore.getState().replaceActivity('loop-1', { ...scriptActivity, id: 'loop-1' })

      const edges = useWorkflowStore.getState().edges
      expect(edges.map((e) => e.id)).toEqual(['e-in'])
    })

    it('preserves compatible edges when replacing a node with the same type', () => {
      const act1 = createScriptActivity({ id: 'act-1', name: 'Script', language: 'python', code: 'print(1)' })
      useWorkflowStore.getState().addActivity(act1)
      useWorkflowStore.setState({
        edges: [
          { id: 'e-out', source: 'act-1', target: 'node-a', sourceHandle: 'source', targetHandle: 'target' },
          { id: 'e-in', source: 'prev-node', target: 'act-1', sourceHandle: 'source', targetHandle: 'target' },
        ] as EdgeConnection[],
      })

      const replacement = createScriptActivity({ id: 'tmp', name: 'REST API', language: 'python', code: 'print(2)' })
      useWorkflowStore.getState().replaceActivity('act-1', { ...replacement, id: 'act-1' })

      const edges = useWorkflowStore.getState().edges
      expect(edges.map((e) => e.id)).toEqual(['e-out', 'e-in'])
    })

    it('bumps workflowVersion and preserves undo history on replace', () => {
      const act1 = createScriptActivity({ id: 'act-1', name: 'Script', language: 'python', code: 'print(1)' })
      useWorkflowStore.getState().addActivity(act1)
      const versionBefore = useWorkflowStore.getState().workflowVersion

      const replacement = createScriptActivity({ id: 'tmp', name: 'REST API', language: 'python', code: 'print(2)' })
      useWorkflowStore.getState().replaceActivity('act-1', { ...replacement, id: 'act-1' })

      const state = useWorkflowStore.getState()
      expect(state.workflowVersion).toBe(versionBefore + 1)
      expect(state._preserveHistoryOnLayout).toBe(true)
    })

    it('prunes stale switch case edges when replacing switch with switch', () => {
      const switchActivity: Activity = {
        type: 'switch',
        id: 'sw-1',
        name: 'Switch',
        parameters: {
          cases: [
            { port: 'case_0', label: 'Path 1', condition: '${a}' },
            { port: 'case_1', label: 'Path 2', condition: '${b}' },
            { port: 'case_2', label: 'Path 3', condition: '${c}' },
          ],
          default_port: 'default',
        },
      }
      useWorkflowStore.getState().addActivity(switchActivity)
      useWorkflowStore.setState({
        edges: [
          {
            id: 'e-case0',
            source: 'sw-1',
            target: 'node-a',
            sourceHandle: 'case_0',
            targetHandle: 'target',
          },
          {
            id: 'e-case1',
            source: 'sw-1',
            target: 'node-b',
            sourceHandle: 'case_1',
            targetHandle: 'target',
          },
          {
            id: 'e-default',
            source: 'sw-1',
            target: 'node-c',
            sourceHandle: 'default',
            targetHandle: 'target',
          },
          {
            id: 'e-in',
            source: 'prev-node',
            target: 'sw-1',
            sourceHandle: 'source',
            targetHandle: 'target',
          },
        ] as EdgeConnection[],
      })

      // getValidSourceHandles(SWITCH) only allows DEFAULT — case_N edges are pruned
      const replacement: Activity = {
        type: 'switch',
        id: 'tmp',
        name: 'Switch',
        parameters: { cases: [{ port: 'case_0', label: 'Path 1', condition: '${a}' }], default_port: 'default' },
      }
      useWorkflowStore.getState().replaceActivity('sw-1', { ...replacement, id: 'sw-1' })

      const edges = useWorkflowStore.getState().edges
      expect(edges.map((e) => e.id).sort()).toEqual(['e-default', 'e-in'])
    })
  })

  describe('updateSwitchActivity', () => {
    const switchActivity: Activity = {
      type: 'switch',
      id: 'switch-1',
      name: 'Route',
      parameters: { cases: [{ port: 'case_0', label: 'Path 1', condition: '${a} == 1' }], default_port: 'default' },
    }

    beforeEach(() => {
      const workflow = makeWorkflow('Test')
      useWorkflowStore.getState().setWorkflow(workflow)
      useWorkflowStore.getState().addActivity(switchActivity)
      useWorkflowStore.setState({
        edges: [
          { id: 'e0', source: 'switch-1', target: 'node-a', sourceHandle: 'case_0' },
          { id: 'e1', source: 'switch-1', target: 'node-b', sourceHandle: 'case_1' },
          { id: 'e-default', source: 'switch-1', target: 'node-d', sourceHandle: 'default' },
          { id: 'e-no-handle', source: 'switch-1', target: 'node-x' },
          { id: 'e-source', source: 'switch-1', target: 'node-y', sourceHandle: 'source' },
          { id: 'e-other', source: 'other-node', target: 'node-z', sourceHandle: 'case_0' },
        ],
      })
    })

    it('remaps switch case edges per portMapping', () => {
      const portMapping = new Map([['case_0', 'case_1']])
      const updated = { ...switchActivity, name: 'Updated' }
      useWorkflowStore.getState().updateSwitchActivity('switch-1', updated, portMapping)

      const edges = useWorkflowStore.getState().edges
      const remapped = edges.find((e) => e.id === 'e0')
      expect(remapped?.sourceHandle).toBe('case_1')
    })

    it('removes switch case edges not in portMapping', () => {
      const portMapping = new Map([['case_0', 'case_0']])
      useWorkflowStore.getState().updateSwitchActivity('switch-1', switchActivity, portMapping)

      const edges = useWorkflowStore.getState().edges
      expect(edges.find((e) => e.id === 'e1')).toBeUndefined()
    })

    it('preserves default handle edges', () => {
      const portMapping = new Map<string, string>()
      useWorkflowStore.getState().updateSwitchActivity('switch-1', switchActivity, portMapping)

      const edges = useWorkflowStore.getState().edges
      expect(edges.find((e) => e.id === 'e-default')?.sourceHandle).toBe('default')
    })

    it('preserves edges without sourceHandle', () => {
      const portMapping = new Map<string, string>()
      useWorkflowStore.getState().updateSwitchActivity('switch-1', switchActivity, portMapping)

      const edges = useWorkflowStore.getState().edges
      expect(edges.find((e) => e.id === 'e-no-handle')).toBeDefined()
    })

    it('preserves non-switch sourceHandle edges', () => {
      const portMapping = new Map<string, string>()
      useWorkflowStore.getState().updateSwitchActivity('switch-1', switchActivity, portMapping)

      const edges = useWorkflowStore.getState().edges
      expect(edges.find((e) => e.id === 'e-source')?.sourceHandle).toBe('source')
    })

    it('does not affect edges from other nodes', () => {
      const portMapping = new Map<string, string>()
      useWorkflowStore.getState().updateSwitchActivity('switch-1', switchActivity, portMapping)

      const edges = useWorkflowStore.getState().edges
      const otherEdge = edges.find((e) => e.id === 'e-other')
      expect(otherEdge?.source).toBe('other-node')
      expect(otherEdge?.sourceHandle).toBe('case_0')
    })

    it('updates the activity atomically with edge remapping', () => {
      const portMapping = new Map([['case_0', 'case_1']])
      const updated = { ...switchActivity, name: 'Renamed' }
      useWorkflowStore.getState().updateSwitchActivity('switch-1', updated, portMapping)

      const activity = useWorkflowStore.getState().currentWorkflow?.workflow.activities.find((a) => a.id === 'switch-1')
      expect(activity?.name).toBe('Renamed')
      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    it('increments workflowVersion for canvas re-render', () => {
      const versionBefore = useWorkflowStore.getState().workflowVersion
      const portMapping = new Map<string, string>()
      useWorkflowStore.getState().updateSwitchActivity('switch-1', switchActivity, portMapping)

      expect(useWorkflowStore.getState().workflowVersion).toBe(versionBefore + 1)
    })
  })

  describe('undo/redo (temporal middleware)', () => {
    beforeEach(() => {
      useWorkflowStore.setState({ _temporalBatchPending: false })
      useWorkflowStore.temporal.getState().resume()
      useWorkflowStore.temporal.getState().clear()
    })

    // Simulate edge sync completing the temporal batch started by addActivity
    function completeTemporalBatch() {
      useWorkflowStore.setState({ _temporalBatchPending: false })
      useWorkflowStore.temporal.getState().resume()
    }

    // --- Activity undo/redo ---

    it('undoes the last activity addition', () => {
      const workflow = makeWorkflow('Test')
      useWorkflowStore.getState().loadWorkflowWithEdges(workflow, [])

      useWorkflowStore
        .getState()
        .addActivity(createScriptActivity({ id: 'a1', name: 'Step 1', language: 'python', code: 'pass' }))
      completeTemporalBatch()
      expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toHaveLength(1)

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toHaveLength(0)
    })

    it('redoes after undo', () => {
      const workflow = makeWorkflow('Test')
      useWorkflowStore.getState().loadWorkflowWithEdges(workflow, [])

      useWorkflowStore
        .getState()
        .addActivity(createScriptActivity({ id: 'a1', name: 'Step 1', language: 'python', code: 'pass' }))
      completeTemporalBatch()

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toHaveLength(0)

      useWorkflowStore.temporal.getState().redo()
      expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toHaveLength(1)
    })

    it('redo works after add-node + position update with skipTracking', () => {
      const workflow = makeWorkflow('Test')
      useWorkflowStore.getState().loadWorkflowWithEdges(workflow, [])

      useWorkflowStore
        .getState()
        .addActivity(createScriptActivity({ id: 'a1', name: 'Step 1', language: 'python', code: 'pass' }))
      completeTemporalBatch()

      // Simulate useNodePositioning placing the node (skipTracking keeps it out of undo stack)
      useWorkflowStore
        .getState()
        .updateNodePositions({ a1: { x: 100, y: 200 } }, { skipTracking: true, markDirty: false })

      // Simulate onLayout storing positions (skipTracking as well)
      useWorkflowStore.getState().updateNodePositions({ a1: { x: 50, y: 0 } }, { skipTracking: true, markDirty: false })

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toHaveLength(0)

      expect(useWorkflowStore.temporal.getState().futureStates.length).toBeGreaterThan(0)

      useWorkflowStore.temporal.getState().redo()
      expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toHaveLength(1)
    })

    it('wrappedUndo preserves redo after clearNodePositions + addActivity', () => {
      const workflow = makeWorkflow('Test')
      useWorkflowStore.getState().loadWorkflowWithEdges(workflow, [])

      // Simulate initial layout storing positions
      useWorkflowStore.getState().updateNodePositions({ n: { x: 10, y: 20 } }, { skipTracking: true, markDirty: false })

      // Simulate CanvasControls Layout click (markDirty: true → clearNodePositions)
      useWorkflowStore.getState().clearNodePositions()

      useWorkflowStore
        .getState()
        .addActivity(createScriptActivity({ id: 'a1', name: 'Step 1', language: 'python', code: 'pass' }))
      completeTemporalBatch()

      // wrappedUndo sets _preserveHistoryOnLayout so clearUndoHistory skips temporal.clear()
      wrappedUndo()
      expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toHaveLength(0)
      expect(useWorkflowStore.getState()._preserveHistoryOnLayout).toBe(true)
      expect(useWorkflowStore.temporal.getState().futureStates.length).toBeGreaterThan(0)
    })

    it('wrappedUndo clears isDirty when all changes are undone', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      expect(useWorkflowStore.getState().isDirty).toBe(false)

      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'changed' }))
      expect(useWorkflowStore.getState().isDirty).toBe(true)

      wrappedUndo()
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBe(0)
      expect(useWorkflowStore.getState().isDirty).toBe(false)
    })

    it('wrappedUndo keeps isDirty true when partial undo leaves history', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('v0'), [])

      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'v1' }))
      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'v2' }))

      wrappedUndo()
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBeGreaterThan(0)
      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    it('wrappedRedo sets isDirty true after re-applying a change', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])

      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'changed' }))
      wrappedUndo()
      expect(useWorkflowStore.getState().isDirty).toBe(false)

      wrappedRedo()
      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    it('wrappedUndo keeps isDirty true when non-temporal dirty changes exist', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])

      useWorkflowStore.getState().markDirty()
      useWorkflowStore
        .getState()
        .addActivity(createScriptActivity({ id: 'a1', name: 'Step 1', language: 'python', code: 'pass' }))
      completeTemporalBatch()

      wrappedUndo()
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBe(0)
      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    it('wrappedUndo keeps isDirty true when undoing past a save point', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('v0'), [])

      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'v1' }))
      useWorkflowStore.getState().markClean()
      expect(useWorkflowStore.getState().isDirty).toBe(false)

      wrappedUndo()
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBe(0)
      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    // --- Edge undo ---

    it('undoes edge changes', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])

      const edges: EdgeConnection[] = [
        { id: 'e1', source: 'a', target: 'b', sourceHandle: 'source', targetHandle: 'target' },
      ]
      useWorkflowStore.getState().setEdges(edges)
      expect(useWorkflowStore.getState().edges).toHaveLength(1)

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().edges).toHaveLength(0)
    })

    // --- Multiple undo steps ---

    it('supports multiple undo steps', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('v0'), [])

      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'v1' }))
      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'v2' }))
      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'v3' }))

      expect(useWorkflowStore.getState().currentWorkflow?.name).toBe('v3')

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().currentWorkflow?.name).toBe('v2')

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().currentWorkflow?.name).toBe('v1')

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().currentWorkflow?.name).toBe('v0')
    })

    // --- Exclusions ---

    it('does not create undo entry for markClean/markDirty (not tracked)', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      const pastBefore = useWorkflowStore.temporal.getState().pastStates.length

      useWorkflowStore.getState().markDirty()
      useWorkflowStore.getState().markClean()

      expect(useWorkflowStore.temporal.getState().pastStates.length).toBe(pastBefore)
    })

    // --- History cleared on workflow load ---

    it('clears history when a new workflow is loaded via setWorkflow', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Workflow 1'), [])
      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'changed' }))
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBeGreaterThan(0)

      useWorkflowStore.getState().setWorkflow(makeWorkflow('Workflow 2'))
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBe(0)
      expect(useWorkflowStore.temporal.getState().futureStates.length).toBe(0)
    })

    it('clears history when a new workflow is loaded via loadWorkflowWithEdges', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Workflow 1'), [])
      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'changed' }))
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBeGreaterThan(0)

      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Workflow 2'), [])
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBe(0)
    })
  })

  describe('replaceWorkflowContent', () => {
    beforeEach(() => {
      useWorkflowStore.setState({ _temporalBatchPending: false, _preserveHistoryOnLayout: false })
      useWorkflowStore.temporal.getState().resume()
      useWorkflowStore.temporal.getState().clear()
    })

    it('replaces workflow and edges', () => {
      const original = makeWorkflow('Original')
      useWorkflowStore.getState().loadWorkflowWithEdges(original, [])

      const replacement = makeWorkflow('Replacement', [
        createScriptActivity({ id: 'a1', name: 'Step', language: 'python', code: 'pass' }),
      ])
      const newEdges: EdgeConnection[] = [
        { id: 'e1', source: 'a', target: 'b', sourceHandle: 'source', targetHandle: 'target' },
      ]
      useWorkflowStore.getState().replaceWorkflowContent(replacement, newEdges)

      const state = useWorkflowStore.getState()
      expect(state.currentWorkflow?.name).toBe('Replacement')
      expect(state.edges).toEqual(newEdges)
    })

    it('increments workflowVersion', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('V1'), [])
      const versionBefore = useWorkflowStore.getState().workflowVersion

      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('V2'), [])

      expect(useWorkflowStore.getState().workflowVersion).toBe(versionBefore + 1)
    })

    it('sets isDirty to true', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Clean'), [])
      expect(useWorkflowStore.getState().isDirty).toBe(false)

      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('Dirty'), [])

      expect(useWorkflowStore.getState().isDirty).toBe(true)
    })

    it('resets nodePositions', () => {
      useWorkflowStore.setState({ nodePositions: { node1: { x: 100, y: 200 } } })

      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('New'), [])

      expect(useWorkflowStore.getState().nodePositions).toEqual({})
    })

    it('sets _preserveHistoryOnLayout to true', () => {
      expect(useWorkflowStore.getState()._preserveHistoryOnLayout).toBe(false)

      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('New'), [])

      expect(useWorkflowStore.getState()._preserveHistoryOnLayout).toBe(true)
    })

    it('preserves undo history (does not clear temporal)', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Initial'), [])
      useWorkflowStore.getState().updateWorkflow((wf) => ({ ...wf, name: 'Changed' }))
      const historyBefore = useWorkflowStore.temporal.getState().pastStates.length
      expect(historyBefore).toBeGreaterThan(0)

      // Resume temporal so replaceWorkflowContent's state change is tracked
      useWorkflowStore.temporal.getState().resume()
      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('Imported'), [])

      // History should still exist (not cleared like loadWorkflowWithEdges does)
      expect(useWorkflowStore.temporal.getState().pastStates.length).toBeGreaterThanOrEqual(historyBefore)
    })
  })

  describe('_positionsUserModified flag', () => {
    beforeEach(() => {
      useWorkflowStore.setState({ _temporalBatchPending: false, _positionsUserModified: false })
      useWorkflowStore.temporal.getState().resume()
      useWorkflowStore.temporal.getState().clear()
    })

    it('is false after setWorkflow', () => {
      useWorkflowStore.getState().setWorkflow(makeWorkflow('Test'))
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(false)
    })

    it('is false after loadWorkflowWithEdges with no positions', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(false)
    })

    it('is true after loadWorkflowWithEdges with positions', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [], { node1: { x: 1, y: 2 } })
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(true)
    })

    it('is false after loadWorkflowWithEdges with empty positions', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [], {})
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(false)
    })

    it('becomes true after updateNodePositions with markDirty:true (user drag)', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(false)

      useWorkflowStore.getState().updateNodePositions({ n: { x: 1, y: 2 } })
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(true)
    })

    it('stays false after updateNodePositions with markDirty:false (auto-layout)', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      useWorkflowStore.getState().updateNodePositions({ n: { x: 1, y: 2 } }, { markDirty: false })
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(false)
    })

    it('becomes false after clearNodePositions', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [], { n: { x: 1, y: 2 } })
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(true)

      useWorkflowStore.getState().clearNodePositions()
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(false)
    })

    it('is true after replaceWorkflowContent with positions', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('New'), [], { n: { x: 1, y: 2 } })
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(true)
    })

    it('is false after replaceWorkflowContent without positions', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('New'), [])
      expect(useWorkflowStore.getState()._positionsUserModified).toBe(false)
    })

    it('nodePositions are restored by undo', () => {
      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('Test'), [])
      useWorkflowStore.getState().updateNodePositions({ n: { x: 1, y: 2 } }, { markDirty: false })

      useWorkflowStore.getState().updateNodePositions({ n: { x: 50, y: 60 } })

      useWorkflowStore.temporal.getState().undo()
      expect(useWorkflowStore.getState().nodePositions).toEqual({ n: { x: 1, y: 2 } })
    })
  })

  describe('validationErrorCount', () => {
    it('initializes to 0', () => {
      expect(useWorkflowStore.getState().validationErrorCount).toBe(0)
    })

    it('updates when setValidationErrorCount is called', () => {
      useWorkflowStore.getState().setValidationErrorCount(5)

      expect(useWorkflowStore.getState().validationErrorCount).toBe(5)
    })

    it('resets to zero when setValidationErrorCount is called with 0', () => {
      useWorkflowStore.getState().setValidationErrorCount(3)
      useWorkflowStore.getState().setValidationErrorCount(0)

      expect(useWorkflowStore.getState().validationErrorCount).toBe(0)
    })

    it('resets when setWorkflow is called', () => {
      useWorkflowStore.getState().setValidationErrorCount(5)

      useWorkflowStore.getState().setWorkflow(makeWorkflow('new-wf'))

      expect(useWorkflowStore.getState().validationErrorCount).toBe(0)
    })

    it('resets when loadWorkflowWithEdges is called', () => {
      useWorkflowStore.getState().setValidationErrorCount(3)

      useWorkflowStore.getState().loadWorkflowWithEdges(makeWorkflow('loaded-wf'), [])

      expect(useWorkflowStore.getState().validationErrorCount).toBe(0)
    })

    it('resets when replaceWorkflowContent is called', () => {
      useWorkflowStore.getState().setValidationErrorCount(4)

      useWorkflowStore.getState().replaceWorkflowContent(makeWorkflow('replaced-wf'), [])

      expect(useWorkflowStore.getState().validationErrorCount).toBe(0)
    })
  })
})

describe('resetAll (workflowStoreActions)', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      currentWorkflow: null,
      workflowVersion: 0,
      edges: [],
      nodePositions: {},
      _positionsUserModified: false,
      isDirty: false,
      validationErrorCount: 0,
    })
    useWorkflowStore.temporal.getState().clear()
  })

  it('clears all workflow state atomically', async () => {
    const { resetAll } = await import('./workflowStoreActions')

    const workflow = makeWorkflow('Dirty Workflow')
    useWorkflowStore.getState().setWorkflow(workflow)
    useWorkflowStore
      .getState()
      .setEdges([{ id: 'e1', source: 'a', target: 'b', sourceHandle: 'out', targetHandle: 'in' }])
    useWorkflowStore.getState().updateNodePositions({ node1: { x: 100, y: 200 } })
    useWorkflowStore.getState().setValidationErrorCount(3)

    expect(useWorkflowStore.getState().isDirty).toBe(true)
    expect(useWorkflowStore.getState().currentWorkflow).not.toBeNull()

    resetAll()

    const state = useWorkflowStore.getState()
    expect(state.currentWorkflow).toBeNull()
    expect(state.projectId).toBeNull()
    expect(state.edges).toEqual([])
    expect(state.nodePositions).toEqual({})
    expect(state._positionsUserModified).toBe(false)
    expect(state.isDirty).toBe(false)
    expect(state.validationErrorCount).toBe(0)
  })

  it('clears temporal undo history', async () => {
    const { resetAll } = await import('./workflowStoreActions')

    const workflow = makeWorkflow('Undo Test')
    useWorkflowStore.getState().loadWorkflowWithEdges(workflow, [])
    useWorkflowStore
      .getState()
      .setEdges([{ id: 'e1', source: 'a', target: 'b', sourceHandle: 'out', targetHandle: 'in' }])

    expect(useWorkflowStore.temporal.getState().pastStates.length).toBeGreaterThan(0)

    resetAll()

    expect(useWorkflowStore.temporal.getState().pastStates.length).toBe(0)
    expect(useWorkflowStore.temporal.getState().futureStates.length).toBe(0)
  })

  it('leaves isDirty as false after reset (prevents navigation blocker re-trigger)', async () => {
    const { resetAll } = await import('./workflowStoreActions')

    useWorkflowStore.getState().setWorkflow(makeWorkflow('Blocker Test'))
    useWorkflowStore.getState().markDirty()

    expect(useWorkflowStore.getState().isDirty).toBe(true)

    resetAll()

    expect(useWorkflowStore.getState().isDirty).toBe(false)
  })
})
