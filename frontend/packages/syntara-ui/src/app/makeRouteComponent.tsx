import { Suspense } from 'react'

import { ErrorBoundary } from '../components/ErrorBoundary'
import { ProtectedRoute } from '../components/ProtectedRoute'
import { SynLoadingState } from '../components/states/SynLoadingState'
import type { PermissionRequirement } from '../hooks/permissionUtils'

export function makeRouteComponent(element: React.ReactNode, routePermission?: PermissionRequirement) {
  return function RouteComponent() {
    const guarded = routePermission ? <ProtectedRoute {...routePermission}>{element}</ProtectedRoute> : element
    return (
      <ErrorBoundary>
        <Suspense fallback={<SynLoadingState />}>{guarded}</Suspense>
      </ErrorBoundary>
    )
  }
}
