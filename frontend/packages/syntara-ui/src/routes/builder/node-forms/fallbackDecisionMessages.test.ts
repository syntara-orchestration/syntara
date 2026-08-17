import { describe, expect, it } from 'vitest'

import { getFallbackDecisionDisabledMessage } from './fallbackDecisionMessages'
import {
  APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP,
  APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT,
} from './shared/nodeFieldHelpText'

describe('getFallbackDecisionDisabledMessage', () => {
  it('returns undefined when continue on failure is effectively enabled', () => {
    expect(getFallbackDecisionDisabledMessage(true, 'admin-default')).toBeUndefined()
    expect(getFallbackDecisionDisabledMessage(true, 'node-explicit')).toBeUndefined()
    expect(getFallbackDecisionDisabledMessage(true, 'system-fallback')).toBeUndefined()
  })

  it('returns explicit-stop copy when the node setting is stop', () => {
    expect(getFallbackDecisionDisabledMessage(false, 'node-explicit')).toBe(APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP)
  })

  it('returns system-default copy when the node uses system default', () => {
    expect(getFallbackDecisionDisabledMessage(false, 'admin-default')).toBe(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT)
    expect(getFallbackDecisionDisabledMessage(false, 'system-fallback')).toBe(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT)
  })
})
