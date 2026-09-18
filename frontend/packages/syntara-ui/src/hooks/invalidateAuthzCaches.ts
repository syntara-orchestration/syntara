import type { QueryClient } from '@tanstack/react-query'

import { detachPromise } from '../utils/detachPromise'

/**
 * Invalidate cached `can_i` and `what_can_i` results after role or
 * assignment mutations so nav/AM gates pick up the new grants.
 */
export function invalidateAuthzCaches(queryClient: QueryClient): void {
  detachPromise(queryClient.invalidateQueries({ queryKey: ['authz', 'can_i'] }))
  detachPromise(queryClient.invalidateQueries({ queryKey: ['authz', 'can_i_node_types'] }))
  detachPromise(queryClient.invalidateQueries({ queryKey: ['all-permissions'] }))
}
