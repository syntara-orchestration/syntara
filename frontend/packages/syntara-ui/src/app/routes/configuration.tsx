import { createRoute, redirect } from '@tanstack/react-router'

import {
  CredentialDetail,
  CredentialDetailsTabRoute,
  CredentialIntegrationsTabRoute,
  CredentialWorkflowsTabRoute,
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

export const credentialDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration/credentials/$credentialId',
  component: makeRouteComponent(<CredentialDetail />),
})

const credentialDetailsIndexRoute = createRoute({
  getParentRoute: () => credentialDetailRoute,
  path: '/',
  component: makeRouteComponent(<CredentialDetailsTabRoute />),
})

export const credentialDetailsRoute = createRoute({
  getParentRoute: () => credentialDetailRoute,
  path: 'details',
  component: makeRouteComponent(<CredentialDetailsTabRoute />),
})

export const credentialWorkflowsRoute = createRoute({
  getParentRoute: () => credentialDetailRoute,
  path: 'workflows',
  component: makeRouteComponent(<CredentialWorkflowsTabRoute />),
})

export const credentialIntegrationsRoute = createRoute({
  getParentRoute: () => credentialDetailRoute,
  path: 'integrations',
  component: makeRouteComponent(<CredentialIntegrationsTabRoute />),
})

const credentialUnknownTabRoute = createRoute({
  getParentRoute: () => credentialDetailRoute,
  path: '$tab',
  beforeLoad: ({ params }) =>
    redirect({
      to: '/configuration/credentials/$credentialId/details',
      params: { credentialId: params.credentialId },
      replace: true,
    }),
})

export const configurationOverviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration',
  beforeLoad: () => redirect({ to: '/configuration/integrations', replace: true }),
})
export const integrationsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration/integrations',
  validateSearch: integrationsSearch,
  component: makeRouteComponent(<Integrations />, { action: 'read', resourceType: 'integration' }),
})
export const configureIntegrationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration/integrations/configure',
  component: makeRouteComponent(<IntegrationForm />, { action: 'create', resourceType: 'integration' }),
})
export const editIntegrationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration/integrations/$integrationId/edit',
  component: makeRouteComponent(<EditIntegration />, { action: 'update', resourceType: 'integration' }),
})
export const integrationDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration/integrations/$integrationId',
  component: makeRouteComponent(<IntegrationDetail />, { action: 'read', resourceType: 'integration' }),
})
export const integrationDetailTabRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration/integrations/$integrationId/$tab',
  component: makeRouteComponent(<IntegrationDetail />, { action: 'read', resourceType: 'integration' }),
})
export const credentialsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration/credentials',
  validateSearch: credentialsSearch,
  component: makeRouteComponent(<Credentials />),
})

export const configurationRoutes = [
  configurationOverviewRoute,
  integrationsRoute,
  configureIntegrationRoute,
  editIntegrationRoute,
  integrationDetailRoute,
  integrationDetailTabRoute,
  credentialsRoute,
  credentialDetailRoute.addChildren([
    credentialDetailsIndexRoute,
    credentialDetailsRoute,
    credentialWorkflowsRoute,
    credentialIntegrationsRoute,
    credentialUnknownTabRoute,
  ]),
]
