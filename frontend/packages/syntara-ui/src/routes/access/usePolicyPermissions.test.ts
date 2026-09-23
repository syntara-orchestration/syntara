import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from './accessClient'
import { usePolicyPermissions } from './usePolicyPermissions'

vi.mock('./accessClient', () => ({ accessFetchClient: { POST: vi.fn() } }))
vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('usePolicyPermissions', () => {
  beforeEach(() => vi.clearAllMocks())

  it('defaults to safe-false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => usePolicyPermissions(), { wrapper: createWrapper() })
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })

  it('returns CRUD permissions and scopes them to the project', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })
    const { result } = renderHook(() => usePolicyPermissions({ resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    for (const action of ['create', 'update', 'delete']) {
      expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
        body: { action, resource_type: 'policy', resource_project: 'proj-1' },
      })
    }
    expect(result.current.tooltips.create).toContain('policy:create')
    expect(result.current.tooltips.update).toContain('policy:update')
    expect(result.current.tooltips.delete).toContain('policy:delete')
  })

  it('returns safe defaults when the request fails', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))
    const { result } = renderHook(() => usePolicyPermissions(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
  })
})
