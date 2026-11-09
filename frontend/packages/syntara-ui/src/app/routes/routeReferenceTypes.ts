import type { ComponentProps } from 'react'

import { SynLink } from '../../components/SynLink'
import type { AppBreadcrumbItem } from '../breadcrumbs/appBreadcrumbItem'
import { tanstackRouter } from '../tanstackRouter'

import * as routeRefs from './routeReferences'

const staticLink: ComponentProps<typeof SynLink> = {
  options: { to: routeRefs.workflowsRoute.fullPath },
  children: 'Workflows',
}

const dynamicLink: ComponentProps<typeof SynLink> = {
  options: { to: routeRefs.executionDetailRoute.fullPath, params: { executionId: 'execution-1' } },
  children: 'Execution',
}

const dynamicBreadcrumb: AppBreadcrumbItem = {
  label: 'User',
  destination: { to: routeRefs.userDetailRoute.fullPath, params: { userId: 'user-1' } },
}

/** Compile-only examples that keep route registration and shared adapters type checked. */
export function verifyRouteReferenceTypes() {
  tanstackRouter.buildLocation({ to: routeRefs.executionDetailRoute.fullPath, params: { executionId: 'execution-1' } })

  // @ts-expect-error Unknown route paths are rejected.
  tanstackRouter.buildLocation({ to: '/not-a-route' })

  // @ts-expect-error Dynamic routes require their path parameters.
  tanstackRouter.buildLocation({ to: routeRefs.executionDetailRoute.fullPath })

  // @ts-expect-error Path parameters must be strings.
  tanstackRouter.buildLocation({ to: routeRefs.executionDetailRoute.fullPath, params: { executionId: 123 } })

  return [staticLink, dynamicLink, dynamicBreadcrumb]
}
