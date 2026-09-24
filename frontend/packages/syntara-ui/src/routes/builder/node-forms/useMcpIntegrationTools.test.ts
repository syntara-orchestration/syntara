import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { integrationsFetchClient } from '../../../client'

import { useMcpIntegrationTools } from './useMcpIntegrationTools'

vi.mock('../../../client', () => ({
  integrationsFetchClient: {
    GET: vi.fn(),
  },
}))

const mockTools = [
  { id: 'tool-1', name: 'list_directory', integration_id: 'int-1', namespaced_name: 'fs.list_directory' },
  { id: 'tool-2', name: 'read_file', integration_id: 'int-1', namespaced_name: 'fs.read_file' },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => QueryClientProvider({ client: queryClient, children })

function setupMock(resources = mockTools) {
  vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
    data: { resources, next: null },
    response: new Response(),
    error: undefined,
  } as never)
}

describe('useMcpIntegrationTools', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('does not query when no integration is selected', () => {
    setupMock()
    const { result } = renderHook(() => useMcpIntegrationTools(undefined), { wrapper })

    expect(result.current.tools).toEqual([])
    expect(result.current.isLoading).toBe(false)
    expect(integrationsFetchClient.GET).not.toHaveBeenCalled()
  })

  it('queries the integration tools endpoint for the selected integration', async () => {
    setupMock()
    const { result } = renderHook(() => useMcpIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(integrationsFetchClient.GET).toHaveBeenCalledWith('/integrations/{integration_id}/tools', {
      params: {
        path: { integration_id: 'int-1' },
        query: expect.objectContaining({ sort: 'name' }) as Record<string, unknown>,
      },
    })
    expect(result.current.tools.map((tool) => tool.name)).toEqual(['list_directory', 'read_file'])
  })

  it('follows pagination cursors', async () => {
    vi.mocked(integrationsFetchClient.GET)
      .mockResolvedValueOnce({
        data: { resources: [mockTools[0]], next: 'cursor-2' },
        response: new Response(),
        error: undefined,
      } as never)
      .mockResolvedValueOnce({
        data: { resources: [mockTools[1]], next: null },
        response: new Response(),
        error: undefined,
      } as never)

    const { result } = renderHook(() => useMcpIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.tools).toHaveLength(2)
    expect(integrationsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('returns an empty list when the integration has no tools', async () => {
    setupMock([])
    const { result } = renderHook(() => useMcpIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.tools).toEqual([])
  })

  it('exposes isError when the query fails', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: undefined,
      response: new Response(),
      error: { detail: 'Server error' },
    } as never)

    const { result } = renderHook(() => useMcpIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })
  })

  it('exposes a working refetch function', async () => {
    setupMock()
    const { result } = renderHook(() => useMcpIntegrationTools('int-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await result.current.refetch()

    expect(integrationsFetchClient.GET).toHaveBeenCalledTimes(2)
  })
})
