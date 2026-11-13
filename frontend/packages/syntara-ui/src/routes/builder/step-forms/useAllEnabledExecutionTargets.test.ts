import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { executionPlaneFetchClient } from '../../../client'

import { useAllEnabledExecutionTargets } from './useAllEnabledExecutionTargets'

vi.mock('../../../client', () => ({
  executionPlaneFetchClient: {
    GET: vi.fn(),
  },
}))

const mockTargets = [
  { id: 'target-2', name: 'worker-west-01', enabled: true },
  { id: 'target-1', name: 'worker-central-01', enabled: true },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => QueryClientProvider({ client: queryClient, children })

function setupMock(resources = mockTargets) {
  vi.mocked(executionPlaneFetchClient.GET).mockResolvedValue({
    data: { resources, next: null },
    response: new Response(),
    error: undefined,
  } as never)
}

describe('useAllEnabledExecutionTargets', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns enabled execution targets and requests sort=name', async () => {
    setupMock()
    const { result } = renderHook(() => useAllEnabledExecutionTargets(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.targets).toHaveLength(2)
    expect(executionPlaneFetchClient.GET).toHaveBeenCalledWith('/api/execution_plane/v1/execution_targets', {
      params: {
        query: expect.objectContaining({
          sort: 'name',
          enabled: 'true',
        }) as Record<string, unknown>,
      },
    })
  })

  it('returns an empty list when the API has no targets', async () => {
    setupMock([])
    const { result } = renderHook(() => useAllEnabledExecutionTargets(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.targets).toEqual([])
  })

  it('exposes isError when the query fails', async () => {
    vi.mocked(executionPlaneFetchClient.GET).mockResolvedValue({
      data: undefined,
      response: new Response(),
      error: { detail: 'Server error' },
    } as never)

    const { result } = renderHook(() => useAllEnabledExecutionTargets(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isError).toBe(true)
  })
})
