import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../../access/accessClient'

import { useAllServiceAccounts } from './useAllServiceAccounts'

vi.mock('../../access/accessClient', () => ({
  accessFetchClient: {
    GET: vi.fn(),
  },
}))

const mockSAs = [
  {
    id: 'sa-1',
    name: 'SA One',
    status: 'active' as const,
    project_id: 'p-1',
    created_by: { id: 'u-1', name: 'user' },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'sa-2',
    name: 'SA Two',
    status: 'active' as const,
    project_id: 'p-1',
    created_by: { id: 'u-1', name: 'user' },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => QueryClientProvider({ client: queryClient, children })

function setupMock(resources = mockSAs) {
  vi.mocked(accessFetchClient.GET).mockResolvedValue({
    data: { resources, next: null },
    response: new Response(),
    error: undefined,
  })
}

describe('useAllServiceAccounts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('returns service accounts from the API', async () => {
    setupMock()
    const { result } = renderHook(() => useAllServiceAccounts(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.serviceAccounts).toHaveLength(2)
    expect(result.current.serviceAccounts[0].name).toBe('SA One')
  })

  it('passes projectId as query parameter', async () => {
    setupMock()
    const { result } = renderHook(() => useAllServiceAccounts('project-123'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(accessFetchClient.GET).toHaveBeenCalledWith('/service_accounts', {
      params: {
        query: expect.objectContaining({ sort: 'name', project_id: 'project-123' }) as Record<string, unknown>,
      },
    })
  })

  it('does not pass project_id when null', async () => {
    setupMock()
    const { result } = renderHook(() => useAllServiceAccounts(null), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(accessFetchClient.GET).toHaveBeenCalledWith('/service_accounts', {
      params: {
        query: expect.objectContaining({ sort: 'name' }) as Record<string, unknown>,
      },
    })
    const call = JSON.stringify(vi.mocked(accessFetchClient.GET).mock.calls[0])
    expect(call).not.toContain('project_id')
  })

  it('returns empty array initially while loading', () => {
    setupMock()
    const { result } = renderHook(() => useAllServiceAccounts(), { wrapper })

    expect(result.current.serviceAccounts).toEqual([])
    expect(result.current.isLoading).toBe(true)
  })

  it('returns refetch function', async () => {
    setupMock()
    const { result } = renderHook(() => useAllServiceAccounts(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(typeof result.current.refetch).toBe('function')
  })

  it('returns empty array when API returns no resources', async () => {
    setupMock([])
    const { result } = renderHook(() => useAllServiceAccounts(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.serviceAccounts).toEqual([])
  })
})
