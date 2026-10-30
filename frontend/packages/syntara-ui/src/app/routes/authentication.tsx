import { createRoute } from '@tanstack/react-router'

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

const identityProviderDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/authentication/identity-providers/$providerId',
  component: makeRouteComponent(<IdentityProviderDetail />),
})

const identityProviderDetailTabRoutes = [
  createRoute({
    getParentRoute: () => identityProviderDetailRoute,
    path: '/',
    component: makeRouteComponent(<IdentityProviderDetailsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => identityProviderDetailRoute,
    path: '/details',
    component: makeRouteComponent(<IdentityProviderDetailsTabRoute />),
  }),
  createRoute({
    getParentRoute: () => identityProviderDetailRoute,
    path: '/group-mapping',
    component: makeRouteComponent(<IdentityProviderGroupMappingTabRoute />),
  }),
  createRoute({
    getParentRoute: () => identityProviderDetailRoute,
    path: '/$tab',
    component: makeRouteComponent(<IdentityProviderUnknownTabRoute />),
  }),
]

export const authenticationRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/authentication',
    component: makeRouteComponent(<Authentication />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/authentication/identity-providers/add',
    component: makeRouteComponent(<AddIdentityProvider />, { action: 'create', resourceType: 'identity-provider' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/authentication/identity-providers/$providerId/edit',
    component: makeRouteComponent(<EditIdentityProvider />, { action: 'update', resourceType: 'identity-provider' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/system-administration/authentication/identity-providers/$providerId/group-mapping/edit',
    component: makeRouteComponent(<EditGroupMapping />),
  }),
  identityProviderDetailRoute.addChildren(identityProviderDetailTabRoutes),
]
