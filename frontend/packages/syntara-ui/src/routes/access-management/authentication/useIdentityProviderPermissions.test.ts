import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../../access/accessClient'

import { useIdentityProviderPermissions } from './useIdentityProviderPermissions'

const CAN_I_ENDPOINT = '/authz/can_i' as const
const RESOURCE_TYPE = 'identity-provider' as const

vi.mock('../../access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('../../../client', () => ({
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

describe('useIdentityProviderPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to safe-false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useIdentityProviderPermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.canTest).toBe(false)
    expect(result.current.canRevoke).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })

  it('returns all true when API grants all permissions', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useIdentityProviderPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    expect(result.current.canTest).toBe(true)
    expect(result.current.canRevoke).toBe(true)
  })

  it('calls can_i with correct action and resource_type', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    renderHook(() => useIdentityProviderPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledTimes(5)
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: RESOURCE_TYPE },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'update', resource_type: RESOURCE_TYPE },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'delete', resource_type: RESOURCE_TYPE },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'test', resource_type: RESOURCE_TYPE },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'execute', resource_type: 'admin:revocation' },
    })
  })

  it('provides standardized tooltip messages including enable and editMapping', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useIdentityProviderPermissions(), { wrapper: createWrapper() })

    const updatePerm = `${RESOURCE_TYPE}:update`
    expect(result.current.tooltips.create).toContain(`${RESOURCE_TYPE}:create`)
    expect(result.current.tooltips.update).toContain(updatePerm)
    expect(result.current.tooltips.enable).toContain(updatePerm)
    expect(result.current.tooltips.delete).toContain(`${RESOURCE_TYPE}:delete`)
    expect(result.current.tooltips.test).toContain(`${RESOURCE_TYPE}:test`)
    expect(result.current.tooltips.editMapping).toContain(updatePerm)
    expect(result.current.tooltips.revoke).toContain('admin:revocation:execute')
  })

  it('returns safe defaults when requests fail', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))

    const { result } = renderHook(() => useIdentityProviderPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.canTest).toBe(false)
    expect(result.current.canRevoke).toBe(false)
  })
})
