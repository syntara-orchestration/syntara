import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'

import { validateFormPromptConnections } from './validateFormPromptConnections'

function formNode(id: string): Activity {
  return {
    id,
    type: ActivityTypeEnum.FORM_PROMPT,
    name: 'Form',
    parameters: { form_definition: { type: 'object' } },
  }
}

describe('validateFormPromptConnections', () => {
  it('reports error when Submitted branch is not connected', () => {
    const activities = [formNode('form-1')]
    const edges: EdgeConnection[] = [
      { id: 'e1', source: 'form-1', target: 'next', sourceHandle: EdgeHandleEnum.FALLBACK },
    ]

    const errors = validateFormPromptConnections(activities, edges)

    expect(errors).toHaveLength(1)
    expect(errors[0].message).toMatch(/Submitted/i)
    expect(errors[0].rule).toBe('form-prompt-connections')
  })

  it('passes when Submitted branch is connected', () => {
    const activities = [formNode('form-1')]
    const edges: EdgeConnection[] = [
      { id: 'e1', source: 'form-1', target: 'next', sourceHandle: EdgeHandleEnum.SUBMITTED },
    ]

    expect(validateFormPromptConnections(activities, edges)).toEqual([])
  })
})
