import { createRoute } from '@tanstack/react-router'

import { CreateExecutionTarget, EditExecutionTarget, ExecutionPlane, ExecutionTargetDetail } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const executionPlaneSearch = listSearchParams.catch({})

export const executionPlaneRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/execution-plane',
    validateSearch: executionPlaneSearch,
    component: makeRouteComponent(<ExecutionPlane />, { action: 'read', resourceType: 'execution_target' }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/execution-plane/create',
    component: makeRouteComponent(<CreateExecutionTarget />, {
      action: 'create',
      resourceType: 'execution_target',
    }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/execution-plane/$executionTargetId/edit',
    component: makeRouteComponent(<EditExecutionTarget />, {
      action: 'update',
      resourceType: 'execution_target',
    }),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/execution-plane/$executionTargetId',
    component: makeRouteComponent(<ExecutionTargetDetail />, { action: 'read', resourceType: 'execution_target' }),
  }),
]
