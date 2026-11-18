import { IntegrationTypeEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
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
    getIntegrations.mockReset()
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

  it('shares the unscoped query for empty and absent project IDs', async () => {
    getIntegrations.mockResolvedValue({ data: { resources: [{ id: 'global', name: 'Global Kafka' }] } })
    const initialProps: { projectId?: string } = {}
    const { result, rerender } = renderHook(
      ({ projectId }) => useAllIntegrations(IntegrationTypeEnum.KAFKA, projectId),
      { wrapper, initialProps }
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    rerender({ projectId: '' })
    expect(result.current.isPending).toBe(false)
    expect(result.current.data?.[0]?.id).toBe('global')
    rerender({})
    expect(getIntegrations).toHaveBeenCalledOnce()
  })

  it('keeps loaded options available during a same-scope background refresh', async () => {
    getIntegrations.mockResolvedValueOnce({ data: { resources: [{ id: 'cached', name: 'Cached Kafka' }] } })
    const { result } = renderHook(() => useAllIntegrations(IntegrationTypeEnum.KAFKA, 'project-a'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0]?.id).toBe('cached')
    // Track fetching before refetch so React Query notifies the hook about its changes.
    expect(result.current.isFetching).toBe(false)

    let completeRefresh: (() => void) | undefined
    getIntegrations.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          completeRefresh = () => resolve({ data: { resources: [{ id: 'fresh', name: 'Fresh Kafka' }] } })
        })
    )
    const pending: { refresh?: Promise<unknown> } = {}
    act(() => {
      pending.refresh = result.current.refetch()
    })
    await waitFor(() => expect(result.current.isFetching).toBe(true))
    expect(result.current.isPending).toBe(false)
    expect(result.current.data?.[0]?.id).toBe('cached')
    expect(getIntegrations).toHaveBeenCalledTimes(2)
    const refresh = pending.refresh
    if (!refresh) throw new Error('Integration refresh did not start')
    await act(async () => {
      completeRefresh?.()
      await refresh
    })
    await waitFor(() => expect(result.current.data?.[0]?.id).toBe('fresh'))
  })

  it('does not carry options into a different project scope', async () => {
    getIntegrations.mockResolvedValueOnce({ data: { resources: [{ id: 'a', name: 'Project A Kafka' }] } })
    let completeProject: (() => void) | undefined
    getIntegrations.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          completeProject = () => resolve({ data: { resources: [{ id: 'b', name: 'Project B Kafka' }] } })
        })
    )
    const { result, rerender } = renderHook(
      ({ projectId }) => useAllIntegrations(IntegrationTypeEnum.KAFKA, projectId),
      { wrapper, initialProps: { projectId: 'project-a' } }
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    rerender({ projectId: 'project-b' })
    expect(result.current.isPending).toBe(true)
    expect(result.current.data).toBeUndefined()
    await act(async () => {
      completeProject?.()
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.data?.[0]?.id).toBe('b'))
    expect(getIntegrations).toHaveBeenLastCalledWith('/kafka_integrations', {
      params: { query: { enabled: true, project_id: 'project-b', limit: 100, cursor: undefined } },
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
