import { createRoute } from '@tanstack/react-router'

import { Approvals } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const approvalsSearch = listSearchParams.catch({})

export const approvalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/approvals',
  validateSearch: approvalsSearch,
  component: makeRouteComponent(<Approvals />),
})

export const approvalsRoutes = [approvalsRoute]
