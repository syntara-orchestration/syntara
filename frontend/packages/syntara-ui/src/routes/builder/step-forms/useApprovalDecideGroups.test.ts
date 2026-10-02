import type { UsersAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
  usersFetchClient: {
    GET: vi.fn(),
  },
}))

import { usersFetchClient } from '../../../client'

import { useApprovalDecideGroups } from './useApprovalDecideGroups'

type GroupDirectoryEntry = UsersAPI.components['schemas']['GroupDirectoryEntry']

const mockGET = vi.mocked(usersFetchClient.GET)

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 0 },
    },
  })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

describe('useApprovalDecideGroups', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches and returns groups from groups/directory endpoint', async () => {
    const mockGroups: GroupDirectoryEntry[] = [
      { id: 'group-1', name: 'approvers' },
      { id: 'group-2', name: 'admins' },
    ]
    mockGET.mockResolvedValueOnce({
      data: { resources: mockGroups, next: null },
      error: undefined,
      response: new Response(),
    })

    const { result } = renderHook(() => useApprovalDecideGroups(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.groups).toEqual(mockGroups)
    expect(result.current.error).toBeNull()
    expect(mockGET).toHaveBeenCalledWith('/groups/directory', {
      params: {
        query: expect.objectContaining({
          sort: 'name',
        }) as Record<string, unknown>,
      },
    })
  })

  it('returns empty groups when no groups exist', async () => {
    mockGET.mockResolvedValueOnce({
      data: { resources: [], next: null },
      error: undefined,
      response: new Response(),
    })

    const { result } = renderHook(() => useApprovalDecideGroups(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.groups).toEqual([])
    expect(result.current.error).toBeNull()
  })

  it('returns loading state initially', () => {
    mockGET.mockReturnValue(new Promise(() => {}) as never)

    const { result } = renderHook(() => useApprovalDecideGroups(), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.groups).toEqual([])
  })
})
