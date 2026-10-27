import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { toolManagerFetchClient } from '../../../client'

import { useAllTools } from './useAllTools'

vi.mock('../../../client', () => ({
  toolManagerFetchClient: {
    GET: vi.fn(),
  },
}))

const mockTools = [
  { id: 'tool-1', name: 'list_repos', namespaced_name: 'github::list_repos', integration_id: 'int-1', enabled: true },
  {
    id: 'tool-2',
    name: 'send_message',
    namespaced_name: 'slack::send_message',
    integration_id: 'int-2',
    enabled: true,
  },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => QueryClientProvider({ client: queryClient, children })

function setupMock(resources = mockTools) {
  vi.mocked(toolManagerFetchClient.GET).mockResolvedValue({
    data: { resources, next: null },
    response: new Response(),
    error: undefined,
  } as never)
}

describe('useAllTools', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns tools from the API', async () => {
    setupMock()
    const { result } = renderHook(() => useAllTools(), { wrapper })

    expect(result.current.tools).toEqual([])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.tools).toHaveLength(2)
    expect(result.current.tools[0].name).toBe('list_repos')
    expect(toolManagerFetchClient.GET).toHaveBeenCalledWith('/tools', {
      params: {
        query: expect.objectContaining({ sort: 'name' }) as Record<string, unknown>,
      },
    })
  })

  it('follows pagination cursors', async () => {
    const page1 = [mockTools[0]]
    const page2 = [mockTools[1]]

    vi.mocked(toolManagerFetchClient.GET)
      .mockResolvedValueOnce({
        data: { resources: page1, next: 'cursor-2' },
        response: new Response(),
        error: undefined,
      } as never)
      .mockResolvedValueOnce({
        data: { resources: page2, next: null },
        response: new Response(),
        error: undefined,
      } as never)

    const { result } = renderHook(() => useAllTools(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.tools).toHaveLength(2)
    expect(toolManagerFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('returns empty array initially while loading', () => {
    setupMock()
    const { result } = renderHook(() => useAllTools(), { wrapper })

    expect(result.current.tools).toEqual([])
    expect(result.current.isLoading).toBe(true)
  })

  it('returns empty array when API returns no resources', async () => {
    setupMock([])
    const { result } = renderHook(() => useAllTools(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.tools).toEqual([])
  })

  it('exposes a working refetch function', async () => {
    setupMock()
    const { result } = renderHook(() => useAllTools(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(typeof result.current.refetch).toBe('function')
    await result.current.refetch()
    expect(toolManagerFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('exposes isError when the query fails', async () => {
    vi.mocked(toolManagerFetchClient.GET).mockResolvedValue({
      data: undefined,
      response: new Response(),
      error: { detail: 'Server error' },
    } as never)

    const { result } = renderHook(() => useAllTools(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isError).toBe(true)
  })
})
