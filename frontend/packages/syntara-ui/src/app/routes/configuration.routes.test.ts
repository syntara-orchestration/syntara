import { describe, expect, it } from 'vitest'

import { configurationRoutes } from './configuration'
import * as routeRefs from './routeReferences'

describe('configurationRoutes', () => {
  // The redirect route is always first in the array
  const redirectRoute = configurationRoutes[0]
  const redirectRouteOpts = redirectRoute.options as { path?: string; beforeLoad?: () => unknown }

  it('has a route registered for /configuration', () => {
    expect(redirectRouteOpts.path).toBe(routeRefs.configurationOverviewRoute.fullPath)
  })

  it('/configuration beforeLoad returns a redirect to /configuration/integrations with replace', () => {
    expect(redirectRouteOpts.beforeLoad).toBeDefined()

    const result = redirectRouteOpts.beforeLoad?.() as { options: { to: string; replace: boolean } }

    expect(result?.options).toMatchObject({
      to: routeRefs.integrationsRoute.fullPath,
      replace: true,
    })
  })
})
