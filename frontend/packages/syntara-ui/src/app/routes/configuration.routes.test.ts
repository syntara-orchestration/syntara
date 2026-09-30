import { describe, expect, it } from 'vitest'

import { AppRoute } from '../AppRoute'

import { configurationRoutes } from './configuration'
import { settingsRoutes } from './settings'

describe('configurationRoutes', () => {
  // The redirect route is always first in the array
  const redirectRoute = configurationRoutes[0]
  const redirectRouteOpts = redirectRoute.options as { path?: string; beforeLoad?: () => unknown }

  it('has a route registered for /configuration', () => {
    expect(redirectRouteOpts.path).toBe(AppRoute.Configuration.Overview)
  })

  it('/configuration beforeLoad returns a redirect to /configuration/integrations with replace', () => {
    expect(redirectRouteOpts.beforeLoad).toBeDefined()

    const result = redirectRouteOpts.beforeLoad?.() as { options: { to: string; replace: boolean } }

    expect(result?.options).toMatchObject({
      to: AppRoute.Configuration.Integrations.Root,
      replace: true,
    })
  })
})

describe('settingsRoutes', () => {
  it('nests the category route below the settings layout route', () => {
    const settingsRoute = settingsRoutes[0]
    const settingsCategoryRoute = settingsRoute.children?.[0]
    const settingsRouteOptions = settingsRoute.options as { path?: string }
    const settingsCategoryRouteOptions = settingsCategoryRoute?.options as { path?: string } | undefined

    expect(settingsRouteOptions.path).toBe(AppRoute.SystemAdministration.Settings)
    expect(settingsCategoryRouteOptions?.path).toBe('/$category')
  })
})
