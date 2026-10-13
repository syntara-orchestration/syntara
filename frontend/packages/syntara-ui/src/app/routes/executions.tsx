import { createRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { ExecutionDetail, Executions } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'
import { listSearchParams } from '../routeSearchParams'

import { rootRoute } from './__root'

const executionsSearch = listSearchParams
  .extend({
    workflow_id: z.string().optional(),
    status: z.string().optional(),
  })
  .catch({})

const executionDetailSearch = z
  .object({
    approval: z.string().optional(),
    form_prompt: z.string().optional(),
    history: z.string().optional(),
  })
  .catch({})

export const executionsRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/executions',
    validateSearch: executionsSearch,
    component: makeRouteComponent(<Executions />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/executions/$executionId',
    validateSearch: executionDetailSearch,
    component: makeRouteComponent(<ExecutionDetail />),
  }),
]
