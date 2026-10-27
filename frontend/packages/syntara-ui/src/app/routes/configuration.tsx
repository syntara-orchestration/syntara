import { createRoute, redirect } from '@tanstack/react-router'

import {
  CredentialDetail,
  Credentials,
  EditIntegration,
  IntegrationDetail,
  IntegrationForm,
  Integrations,
} from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const credentialsSearch = listSearchParams.catch({})
const integrationsSearch = listSearchParams.catch({})

export const configurationRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration',
    beforeLoad: () => redirect({ to: '/configuration/integrations', replace: true }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations',
    validateSearch: integrationsSearch,
    component: makeRouteComponent(<Integrations />, { action: 'read', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations/configure',
    component: makeRouteComponent(<IntegrationForm />, { action: 'create', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations/$integrationId/edit',
    component: makeRouteComponent(<EditIntegration />, { action: 'update', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations/$integrationId',
    component: makeRouteComponent(<IntegrationDetail />, { action: 'read', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations/$integrationId/$tab',
    component: makeRouteComponent(<IntegrationDetail />, { action: 'read', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations/kafka/$integrationId/edit',
    component: makeRouteComponent(<EditIntegration />, { action: 'update', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations/kafka/$integrationId',
    component: makeRouteComponent(<IntegrationDetail />, { action: 'read', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/integrations/kafka/$integrationId/$tab',
    component: makeRouteComponent(<IntegrationDetail />, { action: 'read', resourceType: 'integration' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/credentials',
    validateSearch: credentialsSearch,
    component: makeRouteComponent(<Credentials />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/credentials/$credentialId',
    component: makeRouteComponent(<CredentialDetail />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration/credentials/$credentialId/$tab',
    component: makeRouteComponent(<CredentialDetail />),
  }),
]
