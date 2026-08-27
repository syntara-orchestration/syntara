import { describe, expect, it } from 'vitest'

import { IDP_TYPE_PRESETS, IdpTypeKey } from './idpTypePresets'

describe('IDP_TYPE_PRESETS', () => {
  it('keeps RP-initiated logout disabled for the AAP preset', () => {
    // The AAP push-button setup registers a single OAuth2 application shared by all
    // users. Enabling RP-initiated logout makes AAP delete every API token tied to
    // that shared application on logout, across all users. The preset must default
    // the toggle off; this test fails if it is ever re-enabled.
    expect(IDP_TYPE_PRESETS[IdpTypeKey.AAP].enableRpInitiatedLogout).toBe(false)
  })

  it('leaves RP-initiated logout disabled for the custom preset', () => {
    expect(IDP_TYPE_PRESETS[IdpTypeKey.CUSTOM].enableRpInitiatedLogout).toBe(false)
  })

  it('keeps AAP role mapping enabled for the AAP preset', () => {
    expect(IDP_TYPE_PRESETS[IdpTypeKey.AAP].aapRoleMappingEnabled).toBe(true)
  })
})
