import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from './accessClient'
import { useAllPermissions } from './useAllPermissions'

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

describe('useAllPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns permissions on successful fetch', async () => {
    const mockPermissions = [
      { policy_name: 'admin-policy', effect: 'allow', actions: ['workflow:read'], scope: '*', project: 'default' },
    ]

    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { resources: mockPermissions, next: null },
      error: null,
    })

    const { result } = renderHook(() => useAllPermissions(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.permissions).toEqual(mockPermissions)
    expect(result.current.error).toBeNull()
  })

  it('paginates through multiple pages', async () => {
    const page1 = [{ policy_name: 'policy-a', effect: 'allow', actions: ['read'], scope: '*', project: '' }]
    const page2 = [{ policy_name: 'policy-b', effect: 'deny', actions: ['delete'], scope: 'project', project: 'prod' }]

    vi.mocked(accessFetchClient.POST)
      .mockResolvedValueOnce({ data: { resources: page1, next: 'cursor-1' }, error: null })
      .mockResolvedValueOnce({ data: { resources: page2, next: null }, error: null })

    const { result } = renderHook(() => useAllPermissions(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.permissions).toEqual([...page1, ...page2])
    expect(accessFetchClient.POST).toHaveBeenCalledTimes(2)
  })

  it('returns error when fetch fails', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: undefined,
      error: { detail: 'Forbidden' },
    })

    const { result } = renderHook(() => useAllPermissions(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
  })

  it('is loading initially', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useAllPermissions(), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.permissions).toEqual([])
  })

  it('passes correct POST body parameters', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { resources: [], next: null },
      error: null,
    })

    renderHook(() => useAllPermissions(), { wrapper })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/what_can_i', {
        body: { limit: 100, cursor: undefined },
      })
    })
  })
})
