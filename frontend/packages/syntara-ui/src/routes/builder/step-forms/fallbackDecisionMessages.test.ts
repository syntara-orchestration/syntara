import { describe, expect, it } from 'vitest'

import { getFallbackDecisionDisabledMessage } from './fallbackDecisionMessages'
import {
  APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP,
  APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT,
} from './shared/stepFieldHelpText'

describe('getFallbackDecisionDisabledMessage', () => {
  it('returns explicit-stop copy when the step setting is stop', () => {
    expect(getFallbackDecisionDisabledMessage('node-explicit')).toBe(APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP)
  })

  it('returns system-default copy when the step uses the system default', () => {
    expect(getFallbackDecisionDisabledMessage('admin-default')).toBe(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT)
    expect(getFallbackDecisionDisabledMessage('system-fallback')).toBe(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT)
  })
})
