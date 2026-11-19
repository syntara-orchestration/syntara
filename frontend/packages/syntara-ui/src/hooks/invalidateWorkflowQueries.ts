import type { QueryClient } from '@tanstack/react-query'

/**
 * Invalidate cached workflow GET queries (list, project-scoped list, and
 * detail) so permission retry paths re-read workflow metadata including
 * `step_types`. openapi-react-query keys these as ['get', path, init], so
 * the predicate must match the method prefix. `includes` rather than
 * `startsWith` so the project-scoped `/projects/{id}/workflows` list is
 * refreshed too.
 */
export function invalidateWorkflowQueries(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (query) =>
      query.queryKey[0] === 'get' && typeof query.queryKey[1] === 'string' && query.queryKey[1].includes('/workflows'),
  })
}
