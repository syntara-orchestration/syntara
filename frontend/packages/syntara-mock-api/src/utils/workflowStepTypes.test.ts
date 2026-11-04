import { describe, expect, it } from 'vitest'

import { getWorkflowStepTypes } from './workflowStepTypes'

describe('getWorkflowStepTypes', () => {
  it('returns sorted distinct types from nodes and triggers across definitions', () => {
    expect(
      getWorkflowStepTypes([
        { triggers: [{ type: 'manual_trigger' }], nodes: [{ type: 'script' }, { type: 'wait' }] },
        { triggers: [{ type: 'manual_trigger' }], nodes: [{ type: 'script' }] },
      ])
    ).toEqual(['manual_trigger', 'script', 'wait'])
  })

  it('returns an empty list for valid empty definitions', () => {
    expect(getWorkflowStepTypes([{ triggers: [], nodes: [] }])).toEqual([])
  })
})
