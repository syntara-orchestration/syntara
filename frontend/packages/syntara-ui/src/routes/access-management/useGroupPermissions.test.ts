import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../access/accessClient'

import { useGroupPermissions } from './useGroupPermissions'

const CAN_I_ENDPOINT = '/authz/can_i' as const

vi.mock('../access/accessClient', () => ({
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

describe('useGroupPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to safe-false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useGroupPermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.canManageMembers).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })

  it('returns all true when API grants all permissions', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useGroupPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    expect(result.current.canManageMembers).toBe(true)
  })

  it('calls can_i with correct action and resource_type', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    renderHook(() => useGroupPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledTimes(4)
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'group' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'update', resource_type: 'group' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'delete', resource_type: 'group' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'manage-members', resource_type: 'group' },
    })
  })

  it('provides standardized tooltip messages', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useGroupPermissions(), { wrapper: createWrapper() })

    expect(result.current.tooltips.create).toContain('group:create')
    expect(result.current.tooltips.update).toContain('group:update')
    expect(result.current.tooltips.delete).toContain('group:delete')
    expect(result.current.tooltips.manageMembers).toContain('group:manage-members')
  })

  it('returns safe defaults when requests fail', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))

    const { result } = renderHook(() => useGroupPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canManageMembers).toBe(false)
  })
})
