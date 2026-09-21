import { createRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { Workflows } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const workflowsSearch = listSearchParams
  .extend({
    'name[contains]': z.string().optional(),
    status: z.string().optional(),
    'labels[contains]': z.string().optional(),
  })
  .catch({})

export const workflowsRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/workflows',
    validateSearch: workflowsSearch,
    component: makeRouteComponent(<Workflows />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/route-baseline-negative-probe',
    beforeLoad: () => redirect({ to: '/workflows', replace: true }),
  }),
]
