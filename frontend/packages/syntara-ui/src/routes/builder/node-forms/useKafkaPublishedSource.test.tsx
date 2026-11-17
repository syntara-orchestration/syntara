import { TriggerTypeEnum, type WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { workflowFetchClient } from '../../../client'

import { useKafkaPublishedSource } from './useKafkaPublishedSource'

vi.mock('../../../client', () => ({ workflowFetchClient: { GET: vi.fn() } }))

function version(
  number: number,
  publishedAt?: string,
  topic = 'orders'
): WorkflowAPI.components['schemas']['WorkflowVersionRead'] {
  return {
    id: `v${number}`,
    workflow_id: 'workflow-1',
    version: number,
    schema_version: '2.0',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    last_published_at: publishedAt,
    workflow_definition: {
      triggers: [
        {
          id: 'subscribe',
          type: TriggerTypeEnum.EVENT_SUBSCRIBE,
          parameters: { integration_id: 'integration-1', topic, group_id: 'orders-group' },
        },
      ],
    },
  }
}

function setup(workflowId: string | null = 'workflow-1', triggerId: string | undefined = 'subscribe') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return { ...renderHook(() => useKafkaPublishedSource(workflowId, triggerId), { wrapper }), client }
}

beforeEach(() => {
  vi.mocked(workflowFetchClient.GET).mockReset()
})

describe('Kafka source publication history', () => {
  it('uses publication time rather than version number and follows pagination', async () => {
    vi.mocked(workflowFetchClient.GET)
      .mockResolvedValueOnce({
        data: { resources: [version(4), version(3, '2026-01-02T00:00:00Z', 'old')], next: 'page2' },
        response: new Response(),
      })
      .mockResolvedValueOnce({ data: { resources: [version(1, '2026-01-03T00:00:00Z')] }, response: new Response() })
    const { result } = setup()
    expect(result.current.isChecking).toBe(true)
    await waitFor(() => expect(result.current.isChecking).toBe(false))
    expect(result.current.source).toEqual({ integrationId: 'integration-1', topic: 'orders', groupId: 'orders-group' })
    expect(workflowFetchClient.GET).toHaveBeenLastCalledWith('/workflows/{workflow_id}/versions', {
      params: { path: { workflow_id: 'workflow-1' }, query: { limit: 100, cursor: 'page2' } },
    })
  })

  it('retains the last published source after unpublishing', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: {
        resources: [
          {
            ...version(1, '2026-01-02T00:00:00Z'),
            status: 'previously_published',
            last_unpublished_at: '2026-01-03T00:00:00Z',
          },
        ],
      },
      response: new Response(),
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.source?.topic).toBe('orders'))
  })

  it.each([
    { resources: [] },
    { resources: [version(1)] },
    { resources: [{ ...version(1, '2026-01-02T00:00:00Z'), workflow_definition: { triggers: [] } }] },
  ])('does not lock a source absent from the most recent publication: %j', async ({ resources }) => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({ data: { resources }, response: new Response() })
    const { result } = setup()
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.source).toBeUndefined()
  })

  it('refreshes when workflow publication queries are invalidated', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({ data: { resources: [] }, response: new Response() })
    const { result, client } = setup()
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { resources: [version(1, '2026-01-02T00:00:00Z')] },
      response: new Response(),
    })
    await act(() => client.invalidateQueries({ queryKey: ['get', '/workflows/{workflow_id}/versions'] }))
    await waitFor(() => expect(result.current.source?.topic).toBe('orders'))
  })

  it('reports history failures instead of treating them as an unpublished source', async () => {
    vi.mocked(workflowFetchClient.GET).mockRejectedValue(new Error('Unavailable'))
    const { result } = setup()
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Unavailable')
  })

  it('fails closed when a published version has no usable publication timestamp', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { resources: [{ ...version(1), status: 'published' }] },
      response: new Response(),
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.source).toBeUndefined()
  })

  it('does not query a workflow that has not been saved', () => {
    const { result } = setup(null)
    expect(result.current.isChecking).toBe(false)
    expect(workflowFetchClient.GET).not.toHaveBeenCalled()
  })
})
