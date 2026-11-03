import { IntegrationTypeEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAllIntegrations } from './useAllIntegrations'

const { getIntegrations } = vi.hoisted(() => ({ getIntegrations: vi.fn() }))
vi.mock('../../../client', () => ({ integrationsFetchClient: { GET: getIntegrations } }))
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: Readonly<{ children: ReactNode }>) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

describe('builder integration options', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('loads all Kafka pages with enabled and project visibility filters', async () => {
    getIntegrations
      .mockResolvedValueOnce({ data: { resources: [{ id: 'first', name: 'First' }], next: 'next-page' } })
      .mockResolvedValueOnce({ data: { resources: [{ id: 'second', name: 'Second' }] } })
    const { result } = renderHook(() => useAllIntegrations(IntegrationTypeEnum.KAFKA, 'workflow-project'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.map((item) => item.id)).toEqual(['first', 'second'])
    expect(getIntegrations).toHaveBeenNthCalledWith(1, '/kafka_integrations', {
      params: { query: { enabled: true, project_id: 'workflow-project', limit: 100, cursor: undefined } },
    })
    expect(getIntegrations).toHaveBeenNthCalledWith(2, '/kafka_integrations', {
      params: { query: { enabled: true, project_id: 'workflow-project', limit: 100, cursor: 'next-page' } },
    })
  })

  it('retains MCP type filtering and handles an empty list', async () => {
    getIntegrations.mockResolvedValue({ data: { resources: [] } })
    const { result } = renderHook(() => useAllIntegrations(IntegrationTypeEnum.MCP_SERVER), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
    expect(getIntegrations).toHaveBeenCalledWith('/integrations', {
      params: {
        query: { integration_type: IntegrationTypeEnum.MCP_SERVER, enabled: true, limit: 100, cursor: undefined },
      },
    })
  })

  it('reports a later-page error rather than silently offering an incomplete list', async () => {
    getIntegrations
      .mockResolvedValueOnce({ data: { resources: [{ id: 'first' }], next: 'next-page' } })
      .mockResolvedValueOnce({ error: { title: 'Unavailable' } })
    const { result } = renderHook(() => useAllIntegrations(IntegrationTypeEnum.KAFKA), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })
})
