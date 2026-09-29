import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../../access/accessClient'

import { useServiceAccountPermissions } from './useServiceAccountPermissions'

const CAN_I_ENDPOINT = '/authz/can_i' as const

vi.mock('../../access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useServiceAccountPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to safe-false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useServiceAccountPermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.canRotateSecret).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })

  it('hub chrome only checks create with check_any_project', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useServiceAccountPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.canRotateSecret).toBe(false)
    expect(accessFetchClient.POST).toHaveBeenCalledTimes(1)
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'service_account', check_any_project: true },
    })
  })

  it('scopes destructive actions to resourceProject on detail/row screens', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useServiceAccountPermissions({ resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    expect(result.current.canRotateSecret).toBe(true)
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'service_account', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'update', resource_type: 'service_account', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'delete', resource_type: 'service_account', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'rotate_secret', resource_type: 'service_account', resource_project: 'proj-1' },
    })
    const anyProjectCalls = (
      vi.mocked(accessFetchClient.POST).mock.calls as unknown as Array<
        [string, { body?: { check_any_project?: boolean } }]
      >
    ).filter(([, options]) => options.body?.check_any_project === true)
    expect(anyProjectCalls).toHaveLength(0)
  })

  it('provides standardized tooltip messages', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useServiceAccountPermissions(), { wrapper: createWrapper() })

    expect(result.current.tooltips.create).toContain('service_account:create')
    expect(result.current.tooltips.update).toContain('service_account:update')
    expect(result.current.tooltips.delete).toContain('service_account:delete')
    expect(result.current.tooltips.rotateSecret).toContain('service_account:rotate_secret')
  })

  it('returns safe defaults when requests fail', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))

    const { result } = renderHook(() => useServiceAccountPermissions({ resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.canRotateSecret).toBe(false)
  })
})
