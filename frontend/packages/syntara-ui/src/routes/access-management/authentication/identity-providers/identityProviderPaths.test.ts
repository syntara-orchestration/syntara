import { describe, expect, it } from 'vitest'

import * as routeRefs from '../../../../app/routes/routeReferences'

import {
  identityProviderDetailOptions,
  identityProviderGroupMappingEditOptions,
  identityProviderGroupMappingTabOptions,
} from './identityProviderPaths'

const PROVIDER_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

describe('identity provider route options', () => {
  it('builds detail route options', () => {
    expect(identityProviderDetailOptions(PROVIDER_ID)).toEqual({
      to: routeRefs.identityProviderDetailRoute.fullPath,
      params: { providerId: PROVIDER_ID },
    })
  })

  it('uses the nested group mapping route', () => {
    expect(identityProviderGroupMappingTabOptions(PROVIDER_ID)).toEqual({
      to: routeRefs.identityProviderGroupMappingRoute.fullPath,
      params: { providerId: PROVIDER_ID },
    })
  })

  it('preserves typed query flags on the edit route', () => {
    expect(identityProviderGroupMappingEditOptions(PROVIDER_ID, 'discover')).toEqual({
      to: routeRefs.editIdentityProviderGroupMappingRoute.fullPath,
      params: { providerId: PROVIDER_ID },
      search: { discover: '1' },
    })
  })
})
