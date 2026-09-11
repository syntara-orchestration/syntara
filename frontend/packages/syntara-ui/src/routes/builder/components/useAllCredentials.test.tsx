import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { credentialsFetchClient } from '../../../client'

import { useAllCredentials } from './useAllCredentials'

vi.mock('../../../client', () => ({
  credentialsFetchClient: {
    GET: vi.fn(),
  },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const mockCredentials = [
  { id: 'cred-1', name: 'Production API Key', credential_type_id: 'type-1', enabled: true },
  { id: 'cred-2', name: 'Staging Token', credential_type_id: 'type-2', enabled: true },
]

describe('useAllCredentials', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns credentials on successful fetch', async () => {
    vi.mocked(credentialsFetchClient.GET).mockResolvedValue({
      data: { resources: mockCredentials },
      error: null,
    } as never)

    const { result } = renderHook(() => useAllCredentials(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.credentials).toEqual(mockCredentials)
    expect(result.current.error).toBeNull()
  })

  it('returns empty array when no credentials exist', async () => {
    vi.mocked(credentialsFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: null,
    } as never)

    const { result } = renderHook(() => useAllCredentials(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.credentials).toEqual([])
  })

  it('is loading initially', () => {
    vi.mocked(credentialsFetchClient.GET).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useAllCredentials(), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.credentials).toEqual([])
  })

  it('returns error when fetch fails', async () => {
    vi.mocked(credentialsFetchClient.GET).mockResolvedValue({
      data: undefined,
      error: { detail: 'Forbidden' },
    } as never)

    const { result } = renderHook(() => useAllCredentials(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
  })

  it('paginates through multiple pages until `next` is exhausted', async () => {
    const page1 = [{ id: 'cred-1', name: 'A', credential_type_id: 'type-1', enabled: true }]
    const page2 = [{ id: 'cred-2', name: 'B', credential_type_id: 'type-1', enabled: true }]

    vi.mocked(credentialsFetchClient.GET)
      .mockResolvedValueOnce({ data: { resources: page1, next: 'cursor-1' }, error: null } as never)
      .mockResolvedValueOnce({ data: { resources: page2 }, error: null } as never)

    const { result } = renderHook(() => useAllCredentials(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.credentials).toEqual([...page1, ...page2])
    expect(credentialsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('passes sort and for_action query parameters without project_id when projectId is omitted', async () => {
    vi.mocked(credentialsFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: null,
    } as never)

    renderHook(() => useAllCredentials(), { wrapper })

    await waitFor(() => {
      expect(credentialsFetchClient.GET).toHaveBeenCalledWith('/credentials', {
        params: {
          query: { sort: 'name', for_action: 'use', limit: 100, cursor: undefined },
        },
      })
    })
  })

  it('includes project_id in the query when projectId is provided', async () => {
    vi.mocked(credentialsFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: null,
    } as never)

    renderHook(() => useAllCredentials({ projectId: 'proj-123' }), { wrapper })

    await waitFor(() => {
      expect(credentialsFetchClient.GET).toHaveBeenCalledWith('/credentials', {
        params: {
          query: { sort: 'name', for_action: 'use', limit: 100, cursor: undefined, project_id: 'proj-123' },
        },
      })
    })
  })

  it('uses a separate cache entry per projectId', async () => {
    vi.mocked(credentialsFetchClient.GET).mockResolvedValue({
      data: { resources: mockCredentials },
      error: null,
    } as never)

    const { result, rerender } = renderHook(
      ({ projectId }: { projectId?: string }) => useAllCredentials({ projectId }),
      {
        wrapper,
        initialProps: { projectId: undefined as string | undefined },
      }
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(credentialsFetchClient.GET).toHaveBeenCalledTimes(1)

    rerender({ projectId: 'proj-123' })

    await waitFor(() => expect(credentialsFetchClient.GET).toHaveBeenCalledTimes(2))
  })

  it('provides a refetch function', async () => {
    vi.mocked(credentialsFetchClient.GET).mockResolvedValue({
      data: { resources: mockCredentials },
      error: null,
    } as never)

    const { result } = renderHook(() => useAllCredentials(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(typeof result.current.refetch).toBe('function')
  })
})
