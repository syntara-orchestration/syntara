import { describe, expect, it } from 'vitest'

import type { ActivityState } from '../../workflows/execution/types'

import { resolveFormPromptActivitySnapshot } from './formPromptActivityState'

describe('resolveFormPromptActivitySnapshot', () => {
  it('returns failed status and error details for the canvas node', () => {
    const states = new Map<string, ActivityState>([
      [
        'collect_input',
        {
          activityId: 'collect_input',
          status: 'failed',
          errorDetails: 'Forms API HTTP 422',
        },
      ],
    ])

    expect(resolveFormPromptActivitySnapshot('collect_input', states)).toEqual({
      status: 'failed',
      errorDetails: 'Forms API HTTP 422',
    })
  })
})
