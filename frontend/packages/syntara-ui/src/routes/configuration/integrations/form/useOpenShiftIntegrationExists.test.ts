import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { integrationsFetchClient } from '../../../../client'

import { OPENSHIFT_INTEGRATION_EXISTS_QUERY_KEY, useOpenShiftIntegrationExists } from './useOpenShiftIntegrationExists'

vi.mock('../../../../client', () => ({
  integrationsFetchClient: {
    GET: vi.fn(),
  },
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => QueryClientProvider({ client: queryClient, children })

function setupMock(resources: { id: string; name: string; integration_type: string }[] = []) {
  vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
    data: { resources, next: null },
    response: new Response(),
    error: undefined,
  } as never)
}

describe('useOpenShiftIntegrationExists', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns exists false when no openshift integration is present', async () => {
    setupMock([])
    const { result } = renderHook(() => useOpenShiftIntegrationExists(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.exists).toBe(false)
    expect(integrationsFetchClient.GET).toHaveBeenCalledWith('/integrations', {
      params: {
        query: expect.objectContaining({
          integration_type: 'openshift',
          limit: 1,
        }) as Record<string, unknown>,
      },
    })
  })

  it('returns exists true when an openshift integration is present', async () => {
    setupMock([{ id: 'int-1', name: 'EP Cluster', integration_type: 'openshift' }])
    const { result } = renderHook(() => useOpenShiftIntegrationExists(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.exists).toBe(true)
  })

  it('returns exists false initially while loading', () => {
    setupMock([])
    const { result } = renderHook(() => useOpenShiftIntegrationExists(), { wrapper })

    expect(result.current.exists).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })

  it('exposes isError when the query fails', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: undefined,
      response: new Response(),
      error: { detail: 'Server error' },
    } as never)

    const { result } = renderHook(() => useOpenShiftIntegrationExists(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isError).toBe(true)
    expect(result.current.exists).toBe(false)
  })

  it('exposes a working refetch function', async () => {
    setupMock([])
    const { result } = renderHook(() => useOpenShiftIntegrationExists(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await result.current.refetch()
    expect(integrationsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('uses the shared query key for cache invalidation', () => {
    expect(OPENSHIFT_INTEGRATION_EXISTS_QUERY_KEY).toEqual(['openshift-integration-exists'])
  })
})
