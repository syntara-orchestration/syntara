import { createRoute } from '@tanstack/react-router'
import { z } from 'zod'

import {
  AddIdentityProvider,
  Authentication,
  EditGroupMapping,
  EditIdentityProvider,
  IdentityProviderDetail,
  IdentityProviderDetailsTabRoute,
  IdentityProviderGroupMappingTabRoute,
  IdentityProviderUnknownTabRoute,
} from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'

import { rootRoute } from './__root'

export const identityProviderDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/authentication/identity-providers/$providerId',
  component: makeRouteComponent(<IdentityProviderDetail />),
})

export const identityProviderIndexRoute = createRoute({
  getParentRoute: () => identityProviderDetailRoute,
  path: '/',
  component: makeRouteComponent(<IdentityProviderDetailsTabRoute />),
})
export const identityProviderDetailsRoute = createRoute({
  getParentRoute: () => identityProviderDetailRoute,
  path: '/details',
  component: makeRouteComponent(<IdentityProviderDetailsTabRoute />),
})
export const identityProviderGroupMappingRoute = createRoute({
  getParentRoute: () => identityProviderDetailRoute,
  path: '/group-mapping',
  component: makeRouteComponent(<IdentityProviderGroupMappingTabRoute />),
})
export const identityProviderUnknownTabRoute = createRoute({
  getParentRoute: () => identityProviderDetailRoute,
  path: '/$tab',
  component: makeRouteComponent(<IdentityProviderUnknownTabRoute />),
})

const identityProviderDetailTabRoutes = [
  identityProviderIndexRoute,
  identityProviderDetailsRoute,
  identityProviderGroupMappingRoute,
  identityProviderUnknownTabRoute,
]

export const authenticationRootRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/authentication',
  component: makeRouteComponent(<Authentication />),
})
export const addIdentityProviderRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/authentication/identity-providers/add',
  component: makeRouteComponent(<AddIdentityProvider />, { action: 'create', resourceType: 'identity-provider' }),
})
export const editIdentityProviderRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/authentication/identity-providers/$providerId/edit',
  component: makeRouteComponent(<EditIdentityProvider />, { action: 'update', resourceType: 'identity-provider' }),
})
export const editIdentityProviderGroupMappingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/authentication/identity-providers/$providerId/group-mapping/edit',
  validateSearch: z.object({ discover: z.string().optional(), new: z.string().optional() }).catch({}),
  component: makeRouteComponent(<EditGroupMapping />),
})

export const authenticationRoutes = [
  authenticationRootRoute,
  addIdentityProviderRoute,
  editIdentityProviderRoute,
  editIdentityProviderGroupMappingRoute,
  identityProviderDetailRoute.addChildren(identityProviderDetailTabRoutes),
]
