import { ActivityTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { buildWorkflowNodeActivity, buildWorkflowNodeUpdate } from './workflowWebMcpNodeBuilder'

describe('buildWorkflowNodeActivity', () => {
  it('builds a supported node with sanitized name, parameters, and settings', () => {
    const activity = buildWorkflowNodeActivity({
      type: ActivityTypeEnum.SCRIPT,
      name: '  Script\u0000 step  ',
      parameters: { language: 'python', code: 'print(1)' },
      settings: { timeout: 15 },
    })

    expect(activity).toMatchObject({
      type: ActivityTypeEnum.SCRIPT,
      name: 'Script step',
      parameters: { language: 'python', code: 'print(1)' },
      settings: { timeout: 15 },
    })
    expect(activity.id).toEqual(expect.any(String))
  })

  it('rejects invalid objects, types, names, and secret parameters', () => {
    expect(() => buildWorkflowNodeActivity(null)).toThrow('Workflow node input must be an object.')
    expect(() => buildWorkflowNodeActivity({ type: 'internal_activity', name: 'Hidden' })).toThrow(
      'Workflow node type is not supported.'
    )
    expect(() => buildWorkflowNodeActivity({ type: ActivityTypeEnum.SCRIPT, name: ' ' })).toThrow(
      'Node name is required.'
    )
    expect(() =>
      buildWorkflowNodeActivity({
        type: ActivityTypeEnum.SCRIPT,
        name: 'Script',
        parameters: { api_key: 'sensitive' },
      })
    ).toThrow('Node parameters.api_key may contain a secret. Use a Syntara credential reference instead.')
  })
})

describe('buildWorkflowNodeUpdate', () => {
  const current = {
    id: 'node-1',
    type: ActivityTypeEnum.SCRIPT,
    name: 'Old name',
    parameters: { language: 'python', code: 'old' },
    settings: { timeout: 10, retry_policy: { max_retries: 1, backoff: 'fixed' as const } },
  }

  it('merges parameter and settings patches while preserving nested retry policy values', () => {
    expect(
      buildWorkflowNodeUpdate(current, {
        node_id: 'node-1',
        name: '  New name  ',
        parameters_patch: { code: 'new' },
        settings_patch: { timeout: 20, retry_policy: { max_retries: 3 } },
      })
    ).toEqual({
      parameters: { language: 'python', code: 'new' },
      settings: { timeout: 20, retry_policy: { max_retries: 3, backoff: 'fixed' } },
      name: 'New name',
    })
  })

  it('requires complete parameters when changing node type', () => {
    expect(() => buildWorkflowNodeUpdate(current, { type: ActivityTypeEnum.WAIT })).toThrow(
      'Provide a full parameters object when changing the node type.'
    )
    expect(buildWorkflowNodeUpdate(current, { type: ActivityTypeEnum.WAIT, parameters: { duration: 5 } })).toEqual({
      parameters: { duration: 5 },
      type: ActivityTypeEnum.WAIT,
    })
  })

  it('rejects empty updates, unknown fields, and conflicting parameter inputs', () => {
    expect(() => buildWorkflowNodeUpdate(current, {})).toThrow('Provide at least one field to update.')
    expect(() => buildWorkflowNodeUpdate(current, { name: 'x', unknown: true })).toThrow(
      'Workflow node update field "unknown" is not supported.'
    )
    expect(() => buildWorkflowNodeUpdate(current, { parameters: {}, parameters_patch: {} })).toThrow(
      'Provide parameters or parameters_patch, not both.'
    )
  })
})
