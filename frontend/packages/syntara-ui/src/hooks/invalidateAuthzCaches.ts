import type { QueryClient } from '@tanstack/react-query'

import { detachPromise } from '../utils/detachPromise'

import { NODE_KINDS_QUERY_PATH } from './useNodeKindsQuery'

/**
 * Invalidate cached `can_i`, `what_can_i` and node-kind permission results
 * after role or assignment mutations so nav/AM gates and the add-step panel
 * pick up the new grants.
 */
export function invalidateAuthzCaches(queryClient: QueryClient): void {
  detachPromise(queryClient.invalidateQueries({ queryKey: ['authz', 'can_i'] }))
  detachPromise(queryClient.invalidateQueries({ queryKey: ['all-permissions'] }))
  // Step-type verdicts come from GET /node_kinds, keyed by project.
  detachPromise(queryClient.invalidateQueries({ queryKey: [NODE_KINDS_QUERY_PATH] }))
}
