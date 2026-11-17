import { createRoute, redirect } from '@tanstack/react-router'

import { TasksAccessGate } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const tasksSearch = listSearchParams.catch({})

export const tasksRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/tasks',
    beforeLoad: () => {
      // TanStack Router redirect is thrown, not an Error instance
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      throw redirect({ to: '/tasks/approvals', replace: true })
    },
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/tasks/$tab',
    validateSearch: tasksSearch,
    component: makeRouteComponent(<TasksAccessGate />),
  }),
]
