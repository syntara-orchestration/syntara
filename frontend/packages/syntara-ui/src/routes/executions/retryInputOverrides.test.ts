import { describe, expect, it } from 'vitest'

import type { WorkflowDefShape } from '../builder/useActivityNameMap'

import {
  diffRetryInputOverrides,
  getEffectiveRetryInputs,
  getRetryInputEditorValue,
  getRetryInputOverrideTargets,
  type ExecutionActivity,
} from './retryInputOverrides'

describe('getEffectiveRetryInputs', () => {
  it('applies saved overrides to resolved values without mutating the original inputs', () => {
    const resolvedInputs = { host: 'original.example', retries: 2 }

    expect(getEffectiveRetryInputs(resolvedInputs, { host: 'retry.example' })).toEqual({
      host: 'retry.example',
      retries: 2,
    })
    expect(resolvedInputs).toEqual({ host: 'original.example', retries: 2 })
  })

  it('keeps resolved values when there are no saved overrides', () => {
    expect(getEffectiveRetryInputs({ host: 'original.example' }, undefined)).toEqual({
      host: 'original.example',
    })
  })

  it('returns null until either resolved inputs or overrides are available', () => {
    expect(getEffectiveRetryInputs(null, undefined)).toBeNull()
  })
})

describe('getRetryInputEditorValue', () => {
  it('prefills allowed parameters with saved overrides applied', () => {
    expect(
      getRetryInputEditorValue({ host: 'original.example', retries: 2, extra: true }, { host: 'retry.example' }, [
        'host',
        'retries',
      ])
    ).toBe(JSON.stringify({ host: 'retry.example', retries: 2 }, null, 2))
  })
})

describe('diffRetryInputOverrides', () => {
  it('returns only keys that changed from the resolved inputs', () => {
    expect(
      diffRetryInputOverrides({ host: 'original.example', retries: 2 }, { host: 'retry.example', retries: 2 })
    ).toEqual({
      host: 'retry.example',
    })
  })

  it('returns undefined when the edited values match the original inputs', () => {
    expect(diffRetryInputOverrides({ host: 'original.example' }, { host: 'original.example' })).toBeUndefined()
  })
})

function activityData(
  activity_id: string,
  status: string,
  fields: { completed_at?: string; started_at?: string } = {}
): ExecutionActivity {
  return { activity_id, status, ...fields }
}

function activityExecution(
  activity_name: string,
  status: 'failed' | 'completed',
  created_at?: string
): ExecutionActivity {
  return {
    execution_id: 'execution-1',
    activity_name,
    node_type: 'agentic',
    temporal_activity_id: activity_name,
    status,
    ...(created_at ? { created_at } : {}),
  }
}

function activity(id: string, name: string, parameters: Record<string, unknown> = { input: '' }) {
  return { id, name, type: 'agentic', parameters }
}

describe('getRetryInputOverrideTargets', () => {
  it('finds configurable targets through workflow layouts and nested control-flow nodes', () => {
    const workflowDefinition: WorkflowDefShape = {
      triggers: [activity('trigger', 'Manual trigger')],
      nodes: [
        {
          id: 'parent',
          name: 'Parent',
          parameters: { condition: 'ready' },
          steps: [activity('step-child', 'Child step')],
          then: [activity('then-child', 'Then child')],
          else: [activity('else-child', 'Else child')],
          loop: { do: [activity('loop-body', 'Loop body')] },
          branches: [
            'legacy branch',
            [activity('array-branch', 'Array branch')],
            activity('object-branch', 'Object branch'),
          ],
        },
        activity('without-parameters', 'No parameters', {}),
      ],
      workflow: { activities: [activity('workflow-activity', 'Workflow activity')] },
    }
    const activities: ExecutionActivity[] = [
      activityData('loop-body#iter-0', 'failed', {
        completed_at: '2026-01-01T00:00:00Z',
        started_at: '2026-01-09T00:00:00Z',
      }),
      activityData('loop-body#iter-1', 'failed', { started_at: '2026-01-02T00:00:00Z' }),
      activityData('loop-body#iter-9', 'failed'),
      activityExecution('loop-body#iter-2', 'failed', '2026-01-03T00:00:00Z'),
      activityExecution('loop-body#iter-3', 'completed', '2026-01-04T00:00:00Z'),
      activityData('other-node#iter-1', 'failed', { completed_at: '2026-01-05T00:00:00Z' }),
    ]

    const targets = getRetryInputOverrideTargets(
      [
        'trigger',
        'parent',
        'step-child',
        'then-child',
        'else-child',
        'loop-body',
        'array-branch',
        'object-branch',
        'workflow-activity',
        'without-parameters',
        'missing-node',
      ],
      workflowDefinition,
      new Map([
        ['trigger', 'Trigger from map'],
        ['step-child', 'Child from map'],
      ]),
      activities
    )

    expect(targets).toEqual([
      { id: 'trigger', name: 'Trigger from map', parameterNames: ['input'], failedActivityName: undefined },
      { id: 'parent', name: 'Parent', parameterNames: ['condition'], failedActivityName: undefined },
      { id: 'step-child', name: 'Child from map', parameterNames: ['input'], failedActivityName: undefined },
      { id: 'then-child', name: 'Then child', parameterNames: ['input'], failedActivityName: undefined },
      { id: 'else-child', name: 'Else child', parameterNames: ['input'], failedActivityName: undefined },
      {
        id: 'loop-body',
        name: 'Loop body',
        parameterNames: ['input'],
        failedActivityName: 'loop-body#iter-2',
      },
      { id: 'array-branch', name: 'Array branch', parameterNames: ['input'], failedActivityName: undefined },
      { id: 'object-branch', name: 'Object branch', parameterNames: ['input'], failedActivityName: undefined },
      {
        id: 'workflow-activity',
        name: 'Workflow activity',
        parameterNames: ['input'],
        failedActivityName: undefined,
      },
    ])
  })

  it('uses the node ID as a name and omits a failed occurrence when none matches', () => {
    const workflowDefinition: WorkflowDefShape = { nodes: [{ id: 'unnamed-node', parameters: { value: 1 } }] }

    expect(
      getRetryInputOverrideTargets(['unnamed-node'], workflowDefinition, new Map(), [activityData('other', 'failed')])
    ).toEqual([{ id: 'unnamed-node', name: 'unnamed-node', parameterNames: ['value'], failedActivityName: undefined }])
  })

  it.each([undefined, null])('returns no targets when the workflow definition is %s', (workflowDefinition) => {
    expect(getRetryInputOverrideTargets(['step'], workflowDefinition, new Map(), [])).toEqual([])
  })
})
