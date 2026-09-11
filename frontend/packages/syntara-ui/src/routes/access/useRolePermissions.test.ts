import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from './accessClient'
import { useRolePermissions } from './useRolePermissions'

const CAN_I_ENDPOINT = '/authz/can_i' as const

vi.mock('./accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useRolePermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to safe-false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useRolePermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })

  it('returns all true when API grants all permissions', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useRolePermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
  })

  it('uses system-scoped can_i when no resourceProject is provided', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    renderHook(() => useRolePermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledTimes(3)
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'role' },
    })
    const anyProjectCalls = (
      vi.mocked(accessFetchClient.POST).mock.calls as unknown as Array<
        [string, { body?: { check_any_project?: boolean } }]
      >
    ).filter(([, options]) => options.body?.check_any_project === true)
    expect(anyProjectCalls).toHaveLength(0)
  })

  it('scopes can_i to resourceProject when provided', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    renderHook(() => useRolePermissions({ resourceProject: 'proj-1' }), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
        body: { action: 'create', resource_type: 'role', resource_project: 'proj-1' },
      })
    })
  })

  it('provides standardized tooltip messages', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useRolePermissions(), { wrapper: createWrapper() })

    expect(result.current.tooltips.create).toContain('role:create')
    expect(result.current.tooltips.update).toContain('role:update')
    expect(result.current.tooltips.delete).toContain('role:delete')
  })

  it('returns safe defaults when requests fail', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))

    const { result } = renderHook(() => useRolePermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
  })
})
