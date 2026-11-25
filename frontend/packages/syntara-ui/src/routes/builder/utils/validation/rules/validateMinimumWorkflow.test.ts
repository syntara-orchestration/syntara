import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'

import { validateMinimumWorkflow } from './validateMinimumWorkflow'

describe('validateMinimumWorkflow', () => {
  it('should pass validation when workflow has triggers, activities, and edges', () => {
    const activities: Activity[] = [
      { type: 'script_python', id: 'task-1', name: 'Task 1', parameters: { code: 'print("hello")' } },
    ]
    const edges: EdgeConnection[] = [
      { id: 'trigger-1-task-1', source: 'trigger-1', target: 'task-1', sourceHandle: 'source', targetHandle: 'target' },
    ]
    const triggers = [{ type: 'manual', id: 'trigger-1' }]

    const result = validateMinimumWorkflow(activities, edges, triggers)

    expect(result).toHaveLength(0)
  })

  it('should fail when workflow has no triggers', () => {
    const activities: Activity[] = [
      { type: 'script_python', id: 'task-1', name: 'Task 1', parameters: { code: 'print("hello")' } },
    ]
    const edges: EdgeConnection[] = [
      { id: 'trigger-1-task-1', source: 'trigger-1', target: 'task-1', sourceHandle: 'source', targetHandle: 'target' },
    ]
    const triggers = undefined

    const result = validateMinimumWorkflow(activities, edges, triggers)

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      severity: 'error',
      rule: 'minimum-workflow',
      message: 'Workflow must have at least one trigger to run',
    })
  })

  it('should fail when workflow has empty triggers array', () => {
    const activities: Activity[] = [
      { type: 'script_python', id: 'task-1', name: 'Task 1', parameters: { code: 'print("hello")' } },
    ]
    const edges: EdgeConnection[] = [
      { id: 'trigger-1-task-1', source: 'trigger-1', target: 'task-1', sourceHandle: 'source', targetHandle: 'target' },
    ]
    const triggers: unknown[] = []

    const result = validateMinimumWorkflow(activities, edges, triggers)

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      severity: 'error',
      rule: 'minimum-workflow',
      message: 'Workflow must have at least one trigger to run',
    })
  })

  it('should fail when workflow has no activities', () => {
    const activities: Activity[] = []
    const edges: EdgeConnection[] = []
    const triggers = [{ type: 'manual', id: 'trigger-1' }]

    const result = validateMinimumWorkflow(activities, edges, triggers)

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      severity: 'error',
      rule: 'minimum-workflow',
      message: 'Workflow must have at least one step to run',
    })
  })

  it('should fail when workflow has no edges connecting triggers and activities', () => {
    const activities: Activity[] = [
      { type: 'script_python', id: 'task-1', name: 'Task 1', parameters: { code: 'print("hello")' } },
    ]
    const edges: EdgeConnection[] = []
    const triggers = [{ type: 'manual', id: 'trigger-1' }]

    const result = validateMinimumWorkflow(activities, edges, triggers)

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      severity: 'error',
      rule: 'minimum-workflow',
      message: 'Workflow must have at least one connection between trigger and steps',
    })
  })

  it('should report multiple errors when multiple requirements are missing', () => {
    const activities: Activity[] = []
    const edges: EdgeConnection[] = []
    const triggers = undefined

    const result = validateMinimumWorkflow(activities, edges, triggers)

    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({
      rule: 'minimum-workflow',
      message: 'Workflow must have at least one trigger to run',
    })
    expect(result[1]).toMatchObject({
      rule: 'minimum-workflow',
      message: 'Workflow must have at least one step to run',
    })
  })

  it('should not check for edges when activities or triggers are missing', () => {
    // When we have triggers but no activities, we should only report missing activities
    // not missing connections
    const activities: Activity[] = []
    const edges: EdgeConnection[] = []
    const triggers = [{ type: 'manual', id: 'trigger-1' }]

    const result = validateMinimumWorkflow(activities, edges, triggers)

    expect(result).toHaveLength(1)
    expect(result[0].message).toBe('Workflow must have at least one step to run')
  })
})
