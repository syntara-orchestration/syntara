import { createRootRouteWithContext, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'

import { detachPromise } from '../../utils/detachPromise'
import type { FeatureFlagConfig } from '../../utils/feature-flags'
import { RootLayout } from '../RootLayout'

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
  component: RootLayout,
  notFoundComponent: NotFoundRedirect,
})
