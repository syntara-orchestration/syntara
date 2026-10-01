import { describe, expect, it } from 'vitest'

import { formPromptFallbackDecisionFromBehavior, resolveFormPromptFallbackBehavior } from './formPromptFallbackBehavior'

describe('formPromptFallbackBehavior', () => {
  it('maps legacy fallback_behavior to fallback_decision', () => {
    expect(formPromptFallbackDecisionFromBehavior('fallback')).toBe('fallback')
    expect(formPromptFallbackDecisionFromBehavior('fail')).toBe('submit')
    expect(formPromptFallbackDecisionFromBehavior(undefined)).toBe('submit')
  })

  it('prefers explicit fallback_behavior when resolving', () => {
    expect(resolveFormPromptFallbackBehavior({ fallback_behavior: 'fallback' }, {}, false)).toBe('fallback')
    expect(resolveFormPromptFallbackBehavior({ fallback_behavior: 'fail' }, {}, true)).toBe('fail')
  })

  it('derives behavior from fallback_decision when behavior is absent', () => {
    expect(resolveFormPromptFallbackBehavior({ fallback_decision: 'fallback' }, {}, false)).toBe('fallback')
    expect(resolveFormPromptFallbackBehavior({ fallback_decision: 'submit' }, {}, true)).toBe('fail')
  })

  it('falls back to continue-on-failure when decision fields are unset', () => {
    expect(resolveFormPromptFallbackBehavior({}, undefined, true)).toBe('fail')
    expect(resolveFormPromptFallbackBehavior({}, { continue_on_failure: true }, false)).toBe('fail')
    expect(resolveFormPromptFallbackBehavior({}, { continue_on_failure: false }, true)).toBe('fail')
  })
})
