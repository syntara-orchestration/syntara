import { createRoute } from '@tanstack/react-router'

import { Settings, SettingsCategoryRoute } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'

import { rootRoute } from './__root'

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system-administration/settings',
  component: makeRouteComponent(<Settings />),
})

const settingsCategoryRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: '/$category',
  component: makeRouteComponent(<SettingsCategoryRoute />),
})

export const settingsRoutes = [settingsRoute.addChildren([settingsCategoryRoute])]
