import { ActivityTypeEnum } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'

import { validateFormPromptFallbackBehavior } from './validateFormPromptFallbackBehavior'

vi.mock('../../../../../utils/generateUUID', () => ({
  generateUUID: () => 'uuid',
}))

describe('validateFormPromptFallbackBehavior', () => {
  const edges: EdgeConnection[] = [{ id: 'e1', source: 'form-1', target: 'api-1', sourceHandle: 'fallback' }]

  it('errors when fallback edge exists and effective routing is fail (system COF off)', () => {
    const activities = [
      {
        id: 'form-1',
        type: ActivityTypeEnum.FORM_PROMPT,
        name: 'My Form',
        parameters: { fallback_behavior: 'fail', form_definition: { type: 'object' } },
      },
    ]

    const errors = validateFormPromptFallbackBehavior(activities, edges, { systemContinueOnFailure: false })
    expect(errors).toHaveLength(1)
    expect(errors[0].rule).toBe('form-prompt-fallback-behavior')
    expect(errors[0].message).toContain('My Form')
  })

  it('passes when fallback_behavior is fallback', () => {
    const activities = [
      {
        id: 'form-1',
        type: ActivityTypeEnum.FORM_PROMPT,
        name: 'My Form',
        parameters: { fallback_behavior: 'fallback', form_definition: { type: 'object' } },
      },
    ]

    const errors = validateFormPromptFallbackBehavior(activities, edges, { systemContinueOnFailure: false })
    expect(errors).toHaveLength(0)
  })
})
