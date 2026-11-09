import { createRoute, redirect } from '@tanstack/react-router'

import { FeatureFlagDemo } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'

import { rootRoute, type AppRouterContext } from './__root'
import { workflowsRoute } from './workflows'

export function guardFeatureFlagDemoRoute({ context }: { context: AppRouterContext }) {
  if (context.featureFlags.workflow_builder_qol !== true) {
    // TanStack Router uses thrown redirect objects to stop route loading.
    // eslint-disable-next-line @typescript-eslint/only-throw-error
    throw redirect({ to: workflowsRoute.fullPath, replace: true })
  }
}

export const featureFlagDemoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/feature-flag-demo',
  beforeLoad: guardFeatureFlagDemoRoute,
  component: makeRouteComponent(<FeatureFlagDemo />),
})

export const featureFlagDemoRoutes = [featureFlagDemoRoute]
