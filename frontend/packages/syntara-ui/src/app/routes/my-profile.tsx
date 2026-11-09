import { createRoute } from '@tanstack/react-router'

import { MyProfile } from '../lazyRoutes'
import { makeRouteComponent } from '../makeRouteComponent'

import { rootRoute } from './__root'

export const myProfileRootRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/my-profile',
  component: makeRouteComponent(<MyProfile />),
})
export const myProfileTabRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/my-profile/$tab',
  component: makeRouteComponent(<MyProfile />),
})

export const myProfileRoutes = [myProfileRootRoute, myProfileTabRoute]
