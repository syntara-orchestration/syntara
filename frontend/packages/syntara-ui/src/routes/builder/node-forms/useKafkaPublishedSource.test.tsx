import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { workflowFetchClient } from '../../../client'

import { useKafkaPublishedSource } from './useKafkaPublishedSource'

vi.mock('../../../client', () => ({ workflowFetchClient: { GET: vi.fn() } }))

const source = {
  trigger_node_id: 'subscribe',
  source_id: 'source-1',
  generation: 2,
  configuration_revision: 3,
  integration_id: 'integration-1',
  topic: 'orders',
  group_id: 'effective-custom-group',
}
const response = (sources = [source]) => ({ data: { kafka_subscription_sources: sources }, response: new Response() })

function setup(workflowId: string | null = 'workflow-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return { ...renderHook(() => useKafkaPublishedSource(workflowId, 'subscribe'), { wrapper }), client }
}

beforeEach(() => {
  vi.mocked(workflowFetchClient.GET).mockReset()
})

describe('Kafka source metadata', () => {
  it('reads the effective projected group with one request, independent of version count or omitted definition groups', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      ...response(),
      data: {
        ...response().data,
        current_version: 5001,
        published_version_id: null,
        version: { workflow_definition: { triggers: [{ id: 'subscribe', parameters: { group_id: null } }] } },
      },
    })
    const { result } = setup()
    await waitFor(() => expect(result.current.source).toEqual(source))
    expect(workflowFetchClient.GET).toHaveBeenCalledExactlyOnceWith('/workflows/{workflow_id}', {
      params: { path: { workflow_id: 'workflow-1' } },
    })
  })

  it('unlocks a trigger absent from the current projection', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response([]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.source).toBeUndefined()
  })

  it('does not expose a cached source as confirmed while a replacement is loading', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response())
    const { result, client } = setup()
    await waitFor(() => expect(result.current.source).toEqual(source))
    let finish: (() => void) | undefined
    vi.mocked(workflowFetchClient.GET).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () => resolve(response([{ ...source, source_id: 'source-2', generation: 3, topic: 'replacement' }]))
        })
    )
    let refreshed: Promise<void> | undefined
    act(() => {
      refreshed = client.invalidateQueries({ queryKey: ['get', '/workflows/{workflow_id}'] })
    })
    await waitFor(() => expect(result.current.isChecking).toBe(true))
    expect(result.current.source).toBeUndefined()
    await act(async () => {
      finish?.()
      await refreshed
    })
    await waitFor(() => expect(result.current.source?.topic).toBe('replacement'))
  })

  it('fails closed when the server does not expose projection metadata', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({ data: { version: {} }, response: new Response() })
    const { result } = setup()
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.source).toBeUndefined()
  })

  it('reports lookup failures instead of treating the source as unpublished', async () => {
    vi.mocked(workflowFetchClient.GET).mockRejectedValue(new Error('Unavailable'))
    const { result } = setup()
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('Unavailable')
  })

  it('does not query an unsaved workflow', () => {
    setup(null)
    expect(workflowFetchClient.GET).not.toHaveBeenCalled()
  })
})
