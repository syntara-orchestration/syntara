import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { integrationsFetchClient } from '../../../client'

import { useAllEnabledMcpIntegrations } from './useAllEnabledMcpIntegrations'

vi.mock('../../../client', () => ({
  integrationsFetchClient: {
    GET: vi.fn(),
  },
}))

const mockIntegrations = [
  { id: 'int-1', name: 'GitHub MCP', integration_type: 'mcp_server', enabled: true },
  { id: 'int-2', name: 'Slack MCP', integration_type: 'mcp_server', enabled: true },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => QueryClientProvider({ client: queryClient, children })

function setupMock(resources = mockIntegrations) {
  vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
    data: { resources, next: null },
    response: new Response(),
    error: undefined,
  } as never)
}

describe('useAllEnabledMcpIntegrations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns integrations from the API', async () => {
    setupMock()
    const { result } = renderHook(() => useAllEnabledMcpIntegrations(), { wrapper })

    expect(result.current.integrations).toEqual([])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.integrations).toHaveLength(2)
    expect(result.current.integrations[0].name).toBe('GitHub MCP')
  })

  it('returns integrations when projectId is provided', async () => {
    setupMock()
    const { result } = renderHook(() => useAllEnabledMcpIntegrations('project-123'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.integrations).toHaveLength(2)
    expect(integrationsFetchClient.GET).toHaveBeenCalledWith('/integrations', {
      params: {
        query: expect.objectContaining({ sort: 'name', project_id: 'project-123' }) as Record<string, unknown>,
      },
    })
  })

  it('returns integrations when projectId is omitted', async () => {
    setupMock()
    const { result } = renderHook(() => useAllEnabledMcpIntegrations(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.integrations).toHaveLength(2)
    expect(integrationsFetchClient.GET).toHaveBeenCalledWith('/integrations', {
      params: {
        query: expect.objectContaining({ sort: 'name', integration_type: 'mcp_server', enabled: true }) as Record<
          string,
          unknown
        >,
      },
    })
  })

  it('follows pagination cursors', async () => {
    const page1 = [mockIntegrations[0]]
    const page2 = [mockIntegrations[1]]

    vi.mocked(integrationsFetchClient.GET)
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

    const { result } = renderHook(() => useAllEnabledMcpIntegrations(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.integrations).toHaveLength(2)
    expect(integrationsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('returns empty array initially while loading', () => {
    setupMock()
    const { result } = renderHook(() => useAllEnabledMcpIntegrations(), { wrapper })

    expect(result.current.integrations).toEqual([])
    expect(result.current.isLoading).toBe(true)
  })

  it('returns empty array when API returns no resources', async () => {
    setupMock([])
    const { result } = renderHook(() => useAllEnabledMcpIntegrations(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.integrations).toEqual([])
  })

  it('exposes a working refetch function', async () => {
    setupMock()
    const { result } = renderHook(() => useAllEnabledMcpIntegrations(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(typeof result.current.refetch).toBe('function')
    await result.current.refetch()
    expect(integrationsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('exposes isError when the query fails', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: undefined,
      response: new Response(),
      error: { detail: 'Server error' },
    } as never)

    const { result } = renderHook(() => useAllEnabledMcpIntegrations(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isError).toBe(true)
  })
})
