import { useParams as useTanStackParams } from '@tanstack/react-router'

type DefaultParams = Record<string, string | undefined>

/**
 * @deprecated Use `useParams` from `@tanstack/react-router` with route-specific type params.
 */
export function useParams<T extends DefaultParams = DefaultParams>(): T {
  return useTanStackParams({ strict: false } as Parameters<typeof useTanStackParams>[0]) as T
}
