import type { NavigateOptions, RegisteredRouter } from '@tanstack/react-router'

/** Navigation options validated against the mounted TanStack route tree. */
export type AppRouteNavigationOptions = NavigateOptions<RegisteredRouter, string, string> & { to: string }
