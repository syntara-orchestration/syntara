import { describe, expect, it } from 'vitest'

import { hasTriggerId } from './hasTriggerId'

const triggers = [
  { id: 'trigger-1', type: 'manual_trigger', name: 'Manual', parameters: {} },
  { id: 'trigger-2', type: 'webhook_trigger', name: 'Webhook', parameters: {} },
]

describe('hasTriggerId', () => {
  it('returns true when the trigger list contains the ID', () => {
    expect(hasTriggerId(triggers, 'trigger-2')).toBe(true)
  })

  it('returns false when the trigger list does not contain the ID', () => {
    expect(hasTriggerId(triggers, 'local-only')).toBe(false)
  })

  it('returns false for an undefined trigger ID', () => {
    expect(hasTriggerId(triggers, undefined)).toBe(false)
  })

  it('returns false for an undefined trigger list', () => {
    expect(hasTriggerId(undefined, 'trigger-1')).toBe(false)
  })
})
