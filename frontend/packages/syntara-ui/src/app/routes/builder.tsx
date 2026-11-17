import { createRoute } from '@tanstack/react-router'
import { z } from 'zod'

import { BuilderEdit, BuilderNew } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'

import { rootRoute } from './__root'

const builderEditSearch = z
  .object({
    fromExecution: z.string().optional(),
    linkExecution: z.string().optional(),
  })
  .catch({})

/** `projectId` pre-fills the project picker shown before the builder opens (R18). */
const builderNewSearch = z
  .object({
    projectId: z.string().min(1).optional(),
  })
  .catch({})

export const builderRoutes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/workflow-builder/new',
    validateSearch: builderNewSearch,
    component: makeRouteComponent(<BuilderNew />),
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/workflow-builder/$workflowId',
    validateSearch: builderEditSearch,
    component: makeRouteComponent(<BuilderEdit />),
  }),
]
