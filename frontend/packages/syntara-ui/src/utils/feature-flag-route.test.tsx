import {
  createMemoryHistory,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { AppRoute } from '../app/AppRoute'
import type { AppRouterContext } from '../app/routes/__root'
import { guardFeatureFlagDemoRoute } from '../app/routes/feature-flag-demo'
import { FeatureFlagDemo } from '../routes/feature-flags/feature-flag-demo-page'

import { toFeatureFlagKey } from './feature-flags'

const workflowBuilderQolStorageKey = toFeatureFlagKey('workflow_builder_qol')

function createFeatureFlagRouter() {
  const rootRoute = createRootRouteWithContext<AppRouterContext>()({ component: Outlet })
  const fallbackRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: AppRoute.Workflows.Root,
    component: () => <h1>Workflows</h1>,
  })
  const featureRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: AppRoute.FeatureFlagDemo,
    beforeLoad: guardFeatureFlagDemoRoute,
    component: FeatureFlagDemo,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([fallbackRoute, featureRoute]),
    history: createMemoryHistory({ initialEntries: [AppRoute.FeatureFlagDemo] }),
    context: { featureFlags: {} },
    defaultPendingMinMs: 0,
  })

  return router
}

beforeEach(() => {
  globalThis.localStorage.removeItem(workflowBuilderQolStorageKey)
})

afterEach(() => {
  globalThis.localStorage.removeItem(workflowBuilderQolStorageKey)
})

describe('feature flag route guard', () => {
  it('redirects the demo route to workflows before rendering when the flag is off', async () => {
    const router = createFeatureFlagRouter()

    render(<RouterProvider router={router} context={{ featureFlags: {} }} />)

    expect(await screen.findByRole('heading', { name: 'Workflows' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Feature flag route demo' })).not.toBeInTheDocument()
  })

  it('loads the guarded demo route and has no accessibility violations when the flag is on', async () => {
    globalThis.localStorage.setItem(workflowBuilderQolStorageKey, 'true')
    const router = createFeatureFlagRouter()

    const { container } = render(
      <RouterProvider router={router} context={{ featureFlags: { workflow_builder_qol: true } }} />
    )

    expect(await screen.findByRole('heading', { name: 'Feature flag route demo' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Guarded workflow builder preview' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Workflows' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
