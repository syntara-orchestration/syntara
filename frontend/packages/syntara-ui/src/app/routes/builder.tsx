import { createRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { BuilderEdit, BuilderNew } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'

import { rootRoute } from './__root'

const builderEditSearch = z
  .object({
    fromExecution: z.string().optional(),
    linkExecution: z.string().optional(),
    version: z.string().optional(),
  })
  .catch({})

export const builderNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/workflow-builder/new',
  component: makeRouteComponent(<BuilderNew />),
})
export const builderEditRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/workflow-builder/$workflowId',
  validateSearch: builderEditSearch,
  component: makeRouteComponent(<BuilderEdit />),
})

export const builderRoutes = [builderNewRoute, builderEditRoute]
