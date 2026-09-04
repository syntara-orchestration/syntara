import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../../access/accessClient'

import { useCredentialPermissions } from './useCredentialPermissions'

const CAN_I_ENDPOINT = '/authz/can_i' as const

vi.mock('../../access/accessClient', () => ({
  accessFetchClient: { POST: vi.fn() },
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

function mockCanI(permissions: Record<string, boolean>) {
  vi.mocked(accessFetchClient.POST).mockImplementation(
    (_path: string, options?: { body?: { action?: string; resource_type?: string } }) => {
      const action = options?.body?.action
      const resource = options?.body?.resource_type
      const key = `${resource}:${action}`

      const mapping: Record<string, boolean> = {
        'credential:create': permissions.create ?? true,
        'credential:update': permissions.update ?? true,
        'credential:delete': permissions.delete ?? true,
      }

      return Promise.resolve({ data: { allowed: mapping[key] ?? true } })
    }
  )
}

describe('useCredentialPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses check_any_project for create and system-scoped update/delete without resourceProject', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)

    const { result } = renderHook(() => useCredentialPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'credential', check_any_project: true },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'update', resource_type: 'credential' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'delete', resource_type: 'credential' },
    })
  })

  it('scopes create/update/delete to resourceProject when provided', async () => {
    mockCanI({ create: true, update: true, delete: true })

    const { result } = renderHook(() => useCredentialPermissions({ resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'credential', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'update', resource_type: 'credential', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'delete', resource_type: 'credential', resource_project: 'proj-1' },
    })
    const anyProjectCalls = (
      vi.mocked(accessFetchClient.POST).mock.calls as unknown as Array<
        [string, { body?: { check_any_project?: boolean } }]
      >
    ).filter(([, options]) => options.body?.check_any_project === true)
    expect(anyProjectCalls).toHaveLength(0)
  })

  it('returns all permissions as true when granted', async () => {
    mockCanI({ create: true, update: true, delete: true })

    const { result } = renderHook(() => useCredentialPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
  })

  it('returns canCreate false when credential:create is denied', async () => {
    mockCanI({ create: false, update: true, delete: true })

    const { result } = renderHook(() => useCredentialPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(true)
  })

  it('returns canDelete false when credential:delete is denied', async () => {
    mockCanI({ create: true, update: true, delete: false })

    const { result } = renderHook(() => useCredentialPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canDelete).toBe(false)
  })

  it('defaults to false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useCredentialPermissions(), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.isReadChecking).toBe(true)
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
  })

  it('isReadChecking becomes false when read resolves while other checks are in flight', async () => {
    let resolveRead: (v: unknown) => void
    const readPromise = new Promise((r) => {
      resolveRead = r
    })
    const neverResolve = new Promise(() => {})

    vi.mocked(accessFetchClient.POST).mockImplementation((_path: string, options?: { body?: { action?: string } }) => {
      if (options?.body?.action === 'read') return readPromise
      return neverResolve
    })

    const { result } = renderHook(() => useCredentialPermissions(), { wrapper: createWrapper() })

    expect(result.current.isReadChecking).toBe(true)
    expect(result.current.isLoading).toBe(true)

    resolveRead!({ data: { allowed: true } })

    await waitFor(() => {
      expect(result.current.isReadChecking).toBe(false)
    })
    expect(result.current.isLoading).toBe(true)
    expect(result.current.canRead).toBe(true)
  })

  it('skips all checks and reports isLoading when enabled is false', () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)

    const { result } = renderHook(() => useCredentialPermissions({ enabled: false }), {
      wrapper: createWrapper(),
    })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(accessFetchClient.POST).not.toHaveBeenCalled()
  })

  it('provides tooltip messages for each permission', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useCredentialPermissions(), { wrapper: createWrapper() })

    expect(result.current.tooltips.create).toContain('credential:create')
    expect(result.current.tooltips.update).toContain('credential:update')
    expect(result.current.tooltips.delete).toContain('credential:delete')
  })
})
