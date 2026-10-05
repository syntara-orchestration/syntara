import { createRoute, redirect } from '@tanstack/react-router'

import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const approvalsSearch = listSearchParams.catch({})

export const approvalsRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/approvals',
    validateSearch: approvalsSearch,
    beforeLoad: () => {
      throw redirect({ to: '/tasks/approvals', replace: true })
    },
  }),
]
