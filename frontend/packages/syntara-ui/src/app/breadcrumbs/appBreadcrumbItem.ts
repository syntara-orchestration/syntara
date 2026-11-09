import type { AppRouteNavigationOptions } from '../routeNavigationOptions'

/** One breadcrumb segment. The current page omits `destination`. */
export type AppBreadcrumbItem = {
  readonly label: string
  readonly destination?: AppRouteNavigationOptions
}
