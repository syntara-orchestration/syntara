import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { workflowFetchClient } from '../../client'

import { useAllWorkflows } from './useAllWorkflows'

vi.mock('../../client', () => ({
  workflowFetchClient: {
    GET: vi.fn(),
  },
  workflowClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

describe('useAllWorkflows', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('does not fetch when disabled', () => {
    const { result } = renderHook(() => useAllWorkflows({ enabled: false }), { wrapper })

    expect(result.current.workflows).toEqual([])
    expect(vi.mocked(workflowFetchClient.GET)).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
  })

  it('returns workflows on successful fetch', async () => {
    const mockWorkflows = [{ id: 'wf-1', name: 'Deploy' }]

    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { resources: mockWorkflows },
      error: undefined,
      response: new Response(),
    } as never)

    const { result } = renderHook(() => useAllWorkflows(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.workflows).toEqual(mockWorkflows)
    expect(result.current.error).toBeNull()
  })

  it('paginates through multiple pages', async () => {
    vi.mocked(workflowFetchClient.GET)
      .mockResolvedValueOnce({
        data: { resources: [{ id: 'wf-1', name: 'A' }], next: 'c1' },
        error: undefined,
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: { resources: [{ id: 'wf-2', name: 'B' }] },
        error: undefined,
        response: new Response(),
      } as never)

    const { result } = renderHook(() => useAllWorkflows(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.workflows).toEqual([
      { id: 'wf-1', name: 'A' },
      { id: 'wf-2', name: 'B' },
    ])
    expect(workflowFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('returns error when fetch fails', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: undefined,
      error: { detail: 'Forbidden' },
      response: new Response(null, { status: 403 }),
    } as never)

    const { result } = renderHook(() => useAllWorkflows(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
  })

  it('passes sort and page size', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { resources: [] },
      error: undefined,
      response: new Response(),
    } as never)

    renderHook(() => useAllWorkflows(), { wrapper })

    await waitFor(() => {
      expect(workflowFetchClient.GET).toHaveBeenCalledWith('/workflows', {
        params: { query: { sort: 'name', limit: 100, cursor: undefined } },
      })
    })
  })
})
