import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { invalidateAuthzCaches } from './invalidateAuthzCaches'
import { NODE_KINDS_QUERY_PATH } from './useNodeKindsQuery'

describe('invalidateAuthzCaches', () => {
  it('invalidates can_i, what_can_i and node-kind query keys', () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    invalidateAuthzCaches(queryClient)

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['authz', 'can_i'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['all-permissions'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: [NODE_KINDS_QUERY_PATH] })
    expect(invalidateQueries).toHaveBeenCalledTimes(3)
  })
})
