import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { nodeKindsClient } from '../client'

import { invalidateAuthzCaches } from './invalidateAuthzCaches'
import { NODE_KINDS_QUERY_PATH } from './useNodeKindsQuery'

describe('invalidateAuthzCaches', () => {
  it('invalidates can_i, what_can_i and node-kind query keys', () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    invalidateAuthzCaches(queryClient)

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['authz', 'can_i'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['all-permissions'] })
    expect(invalidateQueries).toHaveBeenCalledTimes(3)
  })

  it('marks every cached per-project node-kind verdict stale', () => {
    const queryClient = new QueryClient()
    // The exact keys useNodeKindsQuery caches under, one per project.
    const keys = ['project-a', 'project-b'].map(
      (projectId) =>
        nodeKindsClient.queryOptions('get', NODE_KINDS_QUERY_PATH, { params: { query: { project_id: projectId } } })
          .queryKey
    )
    for (const queryKey of keys) queryClient.setQueryData(queryKey, [])

    invalidateAuthzCaches(queryClient)

    for (const queryKey of keys) {
      expect(queryClient.getQueryState(queryKey)?.isInvalidated, JSON.stringify(queryKey)).toBe(true)
    }
  })
})
