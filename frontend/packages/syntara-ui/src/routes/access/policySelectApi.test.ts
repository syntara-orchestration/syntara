import { describe, expect, it } from 'vitest'

import { toPolicySelectPageResult } from './policySelectApi'

describe('toPolicySelectPageResult', () => {
  it('maps policy list resources to PolicySelectListItem shape', () => {
    const result = toPolicySelectPageResult({
      data: {
        resources: [
          {
            name: 'workflow-admin',
            description: 'Manage workflows',
            project_id: null,
            is_project_eligible: false,
          },
        ],
        next: 'cursor-2',
      },
    })

    expect(result).toEqual({
      data: {
        next: 'cursor-2',
        resources: [
          {
            name: 'workflow-admin',
            description: 'Manage workflows',
            project_id: null,
            is_project_eligible: false,
          },
        ],
      },
    })
  })

  it('returns error when the fetch response includes an error', () => {
    expect(toPolicySelectPageResult({ error: { detail: 'Unauthorized' } })).toEqual({
      error: { detail: 'Unauthorized' },
    })
  })

  it('returns error when data is missing', () => {
    expect(toPolicySelectPageResult({})).toEqual({ error: 'Empty response' })
  })
})
