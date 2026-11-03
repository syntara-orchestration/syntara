import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../routes/access/accessClient'

import type { PermissionRequirement } from './permissionUtils'
import { usePermissionChecks } from './usePermissionChecks'

vi.mock('../routes/access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
    use: vi.fn(),
  },
}))

vi.mock('../client', () => ({
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

const CHECKS: PermissionRequirement[] = [
  { action: 'read', resourceType: 'setting' },
  { action: 'write', resourceType: 'setting' },
  { action: 'read', resourceType: 'audit' },
]

describe('usePermissionChecks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns all permissions after resolution', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation(
      (_path: string, options: { body: { action: string; resource_type: string } }) => {
        const { action, resource_type } = options.body
        const allowed = !(action === 'write' && resource_type === 'setting')
        return Promise.resolve({ data: { allowed } })
      }
    )

    const { result } = renderHook(() => usePermissionChecks(CHECKS), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.permissions).toEqual({
      'setting:read': true,
      'setting:write': false,
      'audit:read': true,
    })
  })

  it('defaults all permissions to false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => usePermissionChecks(CHECKS), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.permissions).toEqual({
      'setting:read': false,
      'setting:write': false,
      'audit:read': false,
    })
  })

  it('fires one POST per check', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    renderHook(() => usePermissionChecks(CHECKS), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledTimes(3)
    })

    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'setting' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'write', resource_type: 'setting' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'audit' },
    })
  })

  it('returns safe defaults when requests fail', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))

    const { result } = renderHook(() => usePermissionChecks(CHECKS), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.permissions).toEqual({
      'setting:read': false,
      'setting:write': false,
      'audit:read': false,
    })
  })

  it('handles empty checks array', () => {
    const { result } = renderHook(() => usePermissionChecks([]), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.permissions).toEqual({})
    expect(accessFetchClient.POST).not.toHaveBeenCalled()
  })

  it('resets permissions when checks transition to empty', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const wrapper = createWrapper()
    const { result, rerender } = renderHook(({ checks }) => usePermissionChecks(checks), {
      initialProps: { checks: CHECKS },
      wrapper,
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(Object.keys(result.current.permissions).length).toBeGreaterThan(0)

    rerender({ checks: [] })
    expect(result.current.isLoading).toBe(false)
    expect(result.current.permissions).toEqual({})
  })

  it('deduplicates queries with matching parameters', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const duplicateChecks: PermissionRequirement[] = [
      { action: 'read', resourceType: 'setting' },
      { action: 'read', resourceType: 'setting' },
    ]

    const { result } = renderHook(() => usePermissionChecks(duplicateChecks), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(accessFetchClient.POST).toHaveBeenCalledTimes(1)
  })
})
