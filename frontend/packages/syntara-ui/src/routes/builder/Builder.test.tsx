import { TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { useWorkflowStore } from '../../stores/useWorkflowStore'

// Test the workflow store helpers used by Builder
describe('Builder Workflow Store Helpers', () => {
  describe('createManualTrigger', () => {
    it('creates manual trigger without approval', async () => {
      const { createManualTrigger } = await import('../../stores/useWorkflowStore')
      const trigger = createManualTrigger('test-trigger-1')

      expect(trigger.id).toBe('test-trigger-1')
      expect(trigger.type).toBe(TriggerTypeEnum.MANUAL_TRIGGER)
      expect(trigger.parameters).toEqual({})
    })

    it('creates manual trigger with approval flag (ignored in v2)', async () => {
      const { createManualTrigger } = await import('../../stores/useWorkflowStore')
      const trigger = createManualTrigger('test-trigger-2', true)

      expect(trigger.id).toBe('test-trigger-2')
      expect(trigger.type).toBe(TriggerTypeEnum.MANUAL_TRIGGER)
      expect(trigger.parameters).toEqual({})
    })
  })

  describe('createScheduledTrigger', () => {
    it('creates cron-based scheduled trigger', async () => {
      const { createScheduledTrigger } = await import('../../stores/useWorkflowStore')
      const trigger = createScheduledTrigger('test-trigger-3', 'cron', {
        cron: '0 0 * * *',
        timezone: 'UTC',
      })

      expect(trigger.id).toBe('test-trigger-3')
      expect(trigger.type).toBe(TriggerTypeEnum.SCHEDULED)
      expect(trigger.parameters.schedule_type).toBe('cron')
      expect(trigger.parameters.cron).toBe('0 0 * * *')
      expect(trigger.parameters.timezone).toBe('UTC')
    })

    it('creates interval-based scheduled trigger', async () => {
      const { createScheduledTrigger } = await import('../../stores/useWorkflowStore')
      const trigger = createScheduledTrigger('test-trigger-4', 'interval', {
        interval: 'PT1H',
      })

      expect(trigger.id).toBe('test-trigger-4')
      expect(trigger.type).toBe(TriggerTypeEnum.SCHEDULED)
      expect(trigger.parameters.schedule_type).toBe('interval')
      expect(trigger.parameters.interval).toBe('PT1H')
    })
  })

  describe('createEventTrigger', () => {
    it('creates event trigger without filter', async () => {
      const { createEventTrigger } = await import('../../stores/useWorkflowStore')
      const trigger = createEventTrigger({ id: 'test-trigger-6', source: 'github', eventType: 'push' })

      expect(trigger.id).toBe('test-trigger-6')
      expect(trigger.type).toBe('event')
      expect(trigger.parameters.source).toBe('github')
      expect(trigger.parameters.event_type).toBe('push')
      expect(trigger.parameters.filter).toBeUndefined()
    })

    it('creates event trigger with filter', async () => {
      const { createEventTrigger } = await import('../../stores/useWorkflowStore')
      const trigger = createEventTrigger({
        id: 'test-trigger-7',
        source: 'github',
        eventType: 'push',
        filter: { branch: 'main' },
      })

      expect(trigger.id).toBe('test-trigger-7')
      expect(trigger.type).toBe('event')
      expect(trigger.parameters.source).toBe('github')
      expect(trigger.parameters.event_type).toBe('push')
      expect(trigger.parameters.filter).toEqual({ branch: 'main' })
    })
  })

  describe('createScriptActivity', () => {
    it('creates python script activity', async () => {
      const { createScriptActivity } = await import('../../stores/useWorkflowStore')
      const activity = createScriptActivity({
        id: 'task-1',
        name: 'My Script',
        language: 'python',
        code: 'print("Hello")',
      })

      expect(activity.type).toBe('script')
      expect(activity.id).toBe('task-1')
      expect(activity.name).toBe('My Script')
      expect(activity.parameters.language).toBe('python')
      expect(activity.parameters.code).toBe('print("Hello")')
    })

    it('creates javascript script activity', async () => {
      const { createScriptActivity } = await import('../../stores/useWorkflowStore')
      const activity = createScriptActivity({
        id: 'task-2',
        name: 'JS Script',
        language: 'javascript',
        code: 'console.log("Hi")',
      })

      expect(activity.parameters.language).toBe('javascript')
      expect(activity.parameters.code).toBe('console.log("Hi")')
    })
  })

  describe('createApiActivity', () => {
    it('creates API activity without headers or body', async () => {
      const { createApiActivity } = await import('../../stores/useWorkflowStore')
      const activity = createApiActivity({
        id: 'api-1',
        name: 'GET Users',
        method: 'GET',
        url: 'https://api.example.com/users',
      })

      expect(activity.type).toBe('http_request')
      expect(activity.id).toBe('api-1')
      expect(activity.name).toBe('GET Users')
      expect(activity.parameters.method).toBe('GET')
      expect(activity.parameters.url).toBe('https://api.example.com/users')
      expect(activity.parameters.headers).toBeUndefined()
      expect(activity.parameters.body).toBeUndefined()
    })

    it('creates API activity with header entries', async () => {
      const { createApiActivity } = await import('../../stores/useWorkflowStore')
      const activity = createApiActivity({
        id: 'api-2',
        name: 'POST Data',
        method: 'POST',
        url: 'https://api.example.com/data',
        headers: [{ id: 'h1', key: 'Content-Type', value: 'application/json' }],
      })

      expect(activity.parameters.headers).toEqual({ 'Content-Type': 'application/json' })
    })

    it('creates API activity with valid JSON body', async () => {
      const { createApiActivity } = await import('../../stores/useWorkflowStore')
      const body = JSON.stringify({ name: 'Test' })
      const activity = createApiActivity({
        id: 'api-3',
        name: 'POST User',
        method: 'POST',
        url: 'https://api.example.com/users',
        body,
      })

      expect(activity.parameters.body).toEqual({ name: 'Test' })
    })

    it('skips header entries with empty keys', async () => {
      const { createApiActivity } = await import('../../stores/useWorkflowStore')
      const activity = createApiActivity({
        id: 'api-4',
        name: 'POST Data',
        method: 'POST',
        url: 'https://api.example.com/data',
        headers: [{ id: 'h1', key: '', value: 'ignored' }],
      })

      expect(activity.parameters.headers).toBeUndefined()
    })

    it('uses string body when JSON parsing fails', async () => {
      const { createApiActivity } = await import('../../stores/useWorkflowStore')
      const activity = createApiActivity({
        id: 'api-5',
        name: 'POST Text',
        method: 'POST',
        url: 'https://api.example.com/text',
        body: 'plain text',
      })

      expect(activity.parameters.body).toBe('plain text')
    })
  })

  describe('useWorkflowStore', () => {
    it('initializes with null workflow', () => {
      const state = useWorkflowStore.getState()
      expect(state.currentWorkflow).toBeNull()
    })

    it('sets workflow', () => {
      const store = useWorkflowStore
      const mockWorkflow = {
        schema_version: '2.0.0' as const,
        name: 'Test',
        workflow: { activities: [] },
      }

      store.getState().setWorkflow(mockWorkflow)
      expect(store.getState().currentWorkflow).toEqual(mockWorkflow)

      // Cleanup
      store.getState().setWorkflow(null)
    })

    it('adds trigger to workflow', async () => {
      const store = useWorkflowStore
      const { createManualTrigger } = await import('../../stores/useWorkflowStore')

      store.getState().setWorkflow({
        schema_version: '2.0.0' as const,
        name: 'Test',
        workflow: { activities: [] },
      })

      const trigger = createManualTrigger('test-trigger-8')
      store.getState().addTrigger(trigger)

      expect(store.getState().currentWorkflow?.triggers).toHaveLength(1)
      expect(store.getState().currentWorkflow?.triggers?.[0]).toEqual(trigger)

      // Cleanup
      store.getState().setWorkflow(null)
    })

    it('removes trigger from workflow', async () => {
      const store = useWorkflowStore
      const { createManualTrigger } = await import('../../stores/useWorkflowStore')

      store.getState().setWorkflow({
        schema_version: '2.0.0' as const,
        name: 'Test',
        triggers: [createManualTrigger('test-trigger-9'), createManualTrigger('test-trigger-10')],
        workflow: { activities: [] },
      })

      store.getState().removeTrigger(0)

      expect(store.getState().currentWorkflow?.triggers).toHaveLength(1)

      // Cleanup
      store.getState().setWorkflow(null)
    })

    it('adds activity to workflow', async () => {
      const store = useWorkflowStore
      const { createScriptActivity } = await import('../../stores/useWorkflowStore')

      store.getState().setWorkflow({
        schema_version: '2.0.0' as const,
        name: 'Test',
        workflow: { activities: [] },
      })

      const activity = createScriptActivity({
        id: 'task-1',
        name: 'Test Task',
        language: 'python',
        code: 'print("test")',
      })
      store.getState().addActivity(activity)

      expect(store.getState().currentWorkflow?.workflow.activities).toHaveLength(1)
      expect(store.getState().currentWorkflow?.workflow.activities[0]).toEqual(activity)

      // Cleanup
      store.getState().setWorkflow(null)
    })

    it('removes activity from workflow', async () => {
      const store = useWorkflowStore
      const { createScriptActivity } = await import('../../stores/useWorkflowStore')

      const activity1 = createScriptActivity({ id: 'task-1', name: 'Task 1', language: 'python', code: 'print("1")' })
      const activity2 = createScriptActivity({ id: 'task-2', name: 'Task 2', language: 'python', code: 'print("2")' })

      store.getState().setWorkflow({
        schema_version: '2.0.0' as const,
        name: 'Test',
        workflow: { activities: [activity1, activity2] },
      })

      store.getState().removeActivity('task-1')

      expect(store.getState().currentWorkflow?.workflow.activities).toHaveLength(1)
      expect(store.getState().currentWorkflow?.workflow.activities[0].id).toBe('task-2')

      // Cleanup
      store.getState().setWorkflow(null)
    })

    it('updates activity in workflow', async () => {
      const store = useWorkflowStore
      const { createScriptActivity } = await import('../../stores/useWorkflowStore')

      const activity = createScriptActivity({
        id: 'task-1',
        name: 'Original Name',
        language: 'python',
        code: 'print("test")',
      })

      store.getState().setWorkflow({
        schema_version: '2.0.0' as const,
        name: 'Test',
        workflow: { activities: [activity] },
      })

      store.getState().updateActivity('task-1', { name: 'Updated Name' })

      expect(store.getState().currentWorkflow?.workflow.activities[0].name).toBe('Updated Name')

      // Cleanup
      store.getState().setWorkflow(null)
    })
  })
})
