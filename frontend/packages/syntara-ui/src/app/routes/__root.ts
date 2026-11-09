import { createRootRouteWithContext, lazyRouteComponent, useNavigate } from '@tanstack/react-router'
import { Suspense, createElement, useEffect } from 'react'

import { SynLoadingState } from '../../components/states/SynLoadingState'
import { detachPromise } from '../../utils/detachPromise'
import type { FeatureFlagConfig } from '../../utils/feature-flags'

const LazyRootLayout = lazyRouteComponent(() => import('../RootLayout'), 'RootLayout')

function RootLayoutWithSuspense() {
  return createElement(Suspense, { fallback: createElement(SynLoadingState) }, createElement(LazyRootLayout))
}

export type AppRouterContext = {
  featureFlags: FeatureFlagConfig
}

/** Catches unmatched URLs and redirects to /workflows via the router (preserving history). */
function NotFoundRedirect() {
  const navigate = useNavigate()
  useEffect(() => {
    detachPromise(navigate({ to: '/workflows', replace: true }))
  }, [navigate])
  return null
}

export const rootRoute = createRootRouteWithContext<AppRouterContext>()({
  component: RootLayoutWithSuspense,
  notFoundComponent: NotFoundRedirect,
})
