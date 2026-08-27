import { describe, expect, it } from 'vitest'

import { IdpTypeKey, IDP_TYPE_PRESETS } from './idpTypePresets'

describe('IDP_TYPE_PRESETS', () => {
  it('AAP preset disables RP-initiated logout to prevent token wipe', () => {
    expect(IDP_TYPE_PRESETS[IdpTypeKey.AAP].enableRpInitiatedLogout).toBe(false)
  })

  it('custom preset disables RP-initiated logout by default', () => {
    expect(IDP_TYPE_PRESETS[IdpTypeKey.CUSTOM].enableRpInitiatedLogout).toBe(false)
  })
})
