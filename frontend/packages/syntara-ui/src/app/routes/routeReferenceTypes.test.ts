import type { ComponentProps } from 'react'
import { expect, it } from 'vitest'

import { SynLink } from '../../components/SynLink'
import type { AppBreadcrumbItem } from '../breadcrumbs/appBreadcrumbItem'
import type { AppRouteNavigationOptions } from '../routeNavigationOptions'
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
const fallbackRoutes = [routeRefs.identityProviderUnknownTabRoute, routeRefs.serviceAccountDetailUnknownTabRoute]

type IsAssignable<TSource, TDestination> = [TSource] extends [TDestination] ? true : false

type RouteOptionTypeResults = [
  IsAssignable<
    { to: typeof routeRefs.executionDetailRoute.fullPath; params: { executionId: string } },
    AppRouteNavigationOptions
  >,
  IsAssignable<{ to: typeof routeRefs.executionDetailRoute.fullPath }, AppRouteNavigationOptions>,
  IsAssignable<
    { to: typeof routeRefs.executionDetailRoute.fullPath; params: { executionId: number } },
    AppRouteNavigationOptions
  >,
  IsAssignable<{ to: '/not-a-route' }, AppRouteNavigationOptions>,
]

const routeOptionTypeResults: RouteOptionTypeResults = [true, false, false, false]

/** Compile-time examples that keep route registration and shared adapters type checked. */
function verifyRouteReferenceTypes() {
  tanstackRouter.buildLocation({ to: routeRefs.executionDetailRoute.fullPath, params: { executionId: 'execution-1' } })

  // @ts-expect-error Unknown route paths are rejected.
  tanstackRouter.buildLocation({ to: '/not-a-route' })

  // @ts-expect-error Dynamic routes require their path parameters.
  tanstackRouter.buildLocation({ to: routeRefs.executionDetailRoute.fullPath })

  // @ts-expect-error Path parameters must be strings.
  tanstackRouter.buildLocation({ to: routeRefs.executionDetailRoute.fullPath, params: { executionId: 123 } })

  return [staticLink, dynamicLink, dynamicBreadcrumb]
}

it('validates route references and keeps navigation destinations route-safe', () => {
  expect(verifyRouteReferenceTypes()).toHaveLength(3)
  expect(fallbackRoutes).toHaveLength(2)
  expect(routeOptionTypeResults).toEqual([true, false, false, false])
})
