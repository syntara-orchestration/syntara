import { useRouterState } from '@tanstack/react-router'

export function useUrlTab<T extends string = string>(basePath: string, defaultTab: NoInfer<T> = 'details' as T): T {
  const pathname = useRouterState({ select: (s) => s.location.pathname })

  const rest = pathname.startsWith(basePath) ? pathname.slice(basePath.length) : ''
  const tabSlug = (rest.split('/').find(Boolean) ?? defaultTab) as T
  return tabSlug
}
