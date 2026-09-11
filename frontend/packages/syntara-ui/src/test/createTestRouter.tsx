import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import React from 'react'

import { toTanStackPathTemplate } from '../app/convertParamSyntax'

/**
 * Module-scoped context used to pass test children into the matched route's component.
 * Test isolation relies on Vitest's per-file module scope (each test file gets its own
 * `TestChildrenCtx` instance) and React's component-tree-based context resolution
 * (each `TestRouterWrapper` renders its own `Provider`, so renders don't share state).
 */
const TestChildrenCtx = React.createContext<React.ReactNode>(null)

function TestRouteComponent() {
  const children = React.use(TestChildrenCtx)
  return <>{children}</>
}

/**
 * Returns a React wrapper component that provides a TanStack Router memory
 * router pre-set to `initialPath`. Use as the `wrapper` option in `renderHook`
 * or `render` for routing contract tests.
 *
 * `RouterProvider` handles route loading internally; no `await router.load()`
 * is required. Use `waitFor` in tests that assert on navigation side-effects
 * (which are inherently async in TanStack Router).
 *
 * @param initialPath - The initial URL path (may include query string, e.g. "/users?tab=groups")
 * @param routePattern - Optional AppRoute-style path pattern (e.g. "/users/:userId") for
 *   `useParams` tests. Converted to TanStack syntax (`$userId`) automatically.
 *   When omitted, a catch-all route is used so location/navigate/search tests work.
 */
export function createTestRouter(initialPath = '/', routePattern?: string) {
  const history = createMemoryHistory({ initialEntries: [initialPath] })
  const rootRoute = createRootRoute({ component: Outlet })

  const router = createRouter({
    history,
    defaultPendingMinMs: 0,
    routeTree: routePattern
      ? rootRoute.addChildren([
          createRoute({
            getParentRoute: () => rootRoute,
            path: toTanStackPathTemplate(routePattern),
            component: TestRouteComponent,
          }),
        ])
      : rootRoute.addChildren([
          createRoute({
            getParentRoute: () => rootRoute,
            path: '$',
            component: TestRouteComponent,
          }),
        ]),
  })

  function TestRouterWrapper({ children }: Readonly<{ children: React.ReactNode }>) {
    return (
      <TestChildrenCtx.Provider value={children}>
        <RouterProvider router={router} />
      </TestChildrenCtx.Provider>
    )
  }

  return TestRouterWrapper
}
