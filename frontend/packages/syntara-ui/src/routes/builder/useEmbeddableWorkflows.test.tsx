import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useEmbeddableWorkflows } from './useEmbeddableWorkflows'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../access/accessClient', () => ({ accessFetchClient: { GET: get } }))

const wrapper = ({ children }: { children: ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('useEmbeddableWorkflows', () => {
  beforeEach(() => vi.clearAllMocks())

  it('follows cursor pagination and returns only published workflows, excluding the current one', async () => {
    get
      .mockResolvedValueOnce({
        data: {
          resources: [
            { id: '1', published_version_id: 'v' },
            { id: '2', published_version_id: null },
          ],
          next: 'c2',
        },
        error: undefined,
      })
      .mockResolvedValueOnce({
        data: {
          resources: [
            { id: '3', published_version_id: 'v' },
            { id: 'self', published_version_id: 'v' },
          ],
          next: null,
        },
        error: undefined,
      })

    const { result } = renderHook(() => useEmbeddableWorkflows('proj', 'self'), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.workflows.map((w) => w.id)).toEqual(['1', '3'])
    expect(get).toHaveBeenCalledTimes(2)
    const secondQuery = (get.mock.calls[1][1] as { params: { query: Record<string, unknown> } }).params.query
    expect(secondQuery.cursor).toBe('c2')
  })

  it('does not fetch when no project is selected', () => {
    renderHook(() => useEmbeddableWorkflows(undefined, undefined), { wrapper })
    expect(get).not.toHaveBeenCalled()
  })
})
