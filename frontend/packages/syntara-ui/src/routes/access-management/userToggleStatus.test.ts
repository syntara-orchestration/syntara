import { describe, expect, it } from 'vitest'

import { BUILTIN_ADMIN_TOGGLE_DISABLED_REASON, LAST_ADMIN_TOGGLE_DISABLED_REASON } from './adminConstants'
import { computeToggleStatus } from './userToggleStatus'

describe('computeToggleStatus', () => {
  it('allows toggling non-admin users', () => {
    expect(computeToggleStatus(false, true, false, false)).toEqual({
      canToggleStatus: true,
      statusToggleDisabledReason: undefined,
    })
  })

  it('blocks disabling the last admin', () => {
    expect(computeToggleStatus(false, true, false, true)).toEqual({
      canToggleStatus: false,
      statusToggleDisabledReason: LAST_ADMIN_TOGGLE_DISABLED_REASON,
    })
  })

  it('allows re-enabling a disabled last-admin candidate', () => {
    expect(computeToggleStatus(false, false, false, false)).toEqual({
      canToggleStatus: true,
      statusToggleDisabledReason: undefined,
    })
  })

  it('blocks disabling builtin admin when not self', () => {
    expect(computeToggleStatus(true, true, false, false)).toEqual({
      canToggleStatus: false,
      statusToggleDisabledReason: BUILTIN_ADMIN_TOGGLE_DISABLED_REASON,
    })
  })

  it('blocks disabling builtin admin when self is last admin', () => {
    expect(computeToggleStatus(true, true, true, true)).toEqual({
      canToggleStatus: false,
      statusToggleDisabledReason: BUILTIN_ADMIN_TOGGLE_DISABLED_REASON,
    })
  })

  it('allows self to disable builtin admin when other admins exist', () => {
    expect(computeToggleStatus(true, true, true, false)).toEqual({
      canToggleStatus: true,
      statusToggleDisabledReason: undefined,
    })
  })

  it('allows anyone to re-enable a disabled builtin admin', () => {
    expect(computeToggleStatus(true, false, false, false)).toEqual({
      canToggleStatus: true,
      statusToggleDisabledReason: undefined,
    })
  })
})
