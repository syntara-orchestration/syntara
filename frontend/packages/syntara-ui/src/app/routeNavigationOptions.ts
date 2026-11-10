import type { NavigateOptions, RegisteredRouter } from '@tanstack/react-router'

/** Navigation options validated against the mounted TanStack route tree. */
type RegisteredRoutePath = keyof RegisteredRouter['routesByPath']

export type AppRouteNavigationOptions = {
  [TTo in RegisteredRoutePath]: NavigateOptions<RegisteredRouter, string, TTo> & { to: TTo }
}[RegisteredRoutePath]
