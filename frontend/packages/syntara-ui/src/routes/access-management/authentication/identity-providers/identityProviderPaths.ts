import type { AppRouteNavigationOptions } from '../../../../app/routeNavigationOptions'
import * as routeRefs from '../../../../app/routes/routeReferences'

export const GROUP_MAPPING_TAB = 'group-mapping' as const
export type IdentityProviderDetailTab = 'details' | typeof GROUP_MAPPING_TAB

export function identityProviderDetailOptions(providerId: string): AppRouteNavigationOptions {
  return { to: routeRefs.identityProviderDetailRoute.fullPath, params: { providerId } }
}

export function identityProviderEditOptions(providerId: string): AppRouteNavigationOptions {
  return { to: routeRefs.editIdentityProviderRoute.fullPath, params: { providerId } }
}

export function identityProviderTabOptions(
  providerId: string,
  tab: IdentityProviderDetailTab
): AppRouteNavigationOptions {
  return tab === GROUP_MAPPING_TAB
    ? { to: routeRefs.identityProviderGroupMappingRoute.fullPath, params: { providerId } }
    : { to: routeRefs.identityProviderDetailsRoute.fullPath, params: { providerId } }
}

export function identityProviderGroupMappingTabOptions(providerId: string): AppRouteNavigationOptions {
  return { to: routeRefs.identityProviderGroupMappingRoute.fullPath, params: { providerId } }
}

export function identityProviderGroupMappingEditOptions(
  providerId: string,
  search?: 'discover' | 'new'
): AppRouteNavigationOptions {
  const target = { to: routeRefs.editIdentityProviderGroupMappingRoute.fullPath, params: { providerId } }
  if (search === 'discover') return { ...target, search: { discover: '1' } }
  if (search === 'new') return { ...target, search: { new: '1' } }
  return target
}
