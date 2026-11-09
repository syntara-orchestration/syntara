import { createRouter } from '@tanstack/react-router'

import { buildTanStackRouteTree } from './tanstackRouteTree'

/**
 * Module-scoped TanStack Router instance.
 *
 * Created once at import time so it can be used both inside React (via
 * `<RouterProvider router={tanstackRouter} />`) and outside React (imperative
 * `tanstackRouter.navigate(...)` in bridge hooks and UnsavedChangesProvider).
 */
export const tanstackRouter = createRouter({
  routeTree: buildTanStackRouteTree(),
  // RouterProvider supplies the current snapshot from FeatureFlagsProvider.
  context: { featureFlags: {} },
})

declare module '@tanstack/react-router' {
  // TanStack Router requires interface augmentation for the global router type.
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  interface Register {
    router: typeof tanstackRouter
  }
}
