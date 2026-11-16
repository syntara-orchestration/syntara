import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { integrationsFetchClient } from '../../../../client'

import { useAllIntegrationTools } from './useAllIntegrationTools'

vi.mock('../../../../client', () => ({
  integrationsFetchClient: {
    GET: vi.fn(),
    use: vi.fn(),
  },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const mockTools = [
  { id: 't1', name: 'get_repo', description: 'Get a repo', enabled: true },
  { id: 't2', name: 'create_pr', description: 'Create PR', enabled: false },
]

describe('useAllIntegrationTools', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns tools on successful fetch', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: { resources: mockTools },
      error: null,
    } as never)

    const { result } = renderHook(() => useAllIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.tools).toEqual(mockTools)
    expect(result.current.error).toBeNull()
  })

  it('paginates through multiple pages', async () => {
    const page1 = [{ id: 't1', name: 'tool_a', description: '', enabled: true }]
    const page2 = [{ id: 't2', name: 'tool_b', description: '', enabled: false }]

    vi.mocked(integrationsFetchClient.GET)
      .mockResolvedValueOnce({ data: { resources: page1, next: 'cursor-1' }, error: null } as never)
      .mockResolvedValueOnce({ data: { resources: page2 }, error: null } as never)

    const { result } = renderHook(() => useAllIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.tools).toEqual([...page1, ...page2])
    expect(integrationsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('returns error when fetch fails', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: undefined,
      error: { detail: 'Forbidden' },
    } as never)

    const { result } = renderHook(() => useAllIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
  })

  it('is loading initially', () => {
    vi.mocked(integrationsFetchClient.GET).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useAllIntegrationTools('int-1'), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.tools).toEqual([])
  })

  it('does not fetch when integrationId is empty', () => {
    const { result } = renderHook(() => useAllIntegrationTools(''), { wrapper })

    expect(result.current.tools).toEqual([])
    expect(integrationsFetchClient.GET).not.toHaveBeenCalled()
  })

  it('passes integration_id in path parameters', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: null,
    } as never)

    renderHook(() => useAllIntegrationTools('int-42'), { wrapper })

    await waitFor(() => {
      expect(integrationsFetchClient.GET).toHaveBeenCalled()
    })

    const call = vi.mocked(integrationsFetchClient.GET).mock.calls[0] as [string, Record<string, unknown>]
    expect(call[0]).toBe('/integrations/{integration_id}/tools')
    expect(call[1]).toMatchObject({
      params: { path: { integration_id: 'int-42' } },
    })
  })
})
