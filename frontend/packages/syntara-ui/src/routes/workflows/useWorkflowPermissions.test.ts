import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../access/accessClient'

import { useWorkflowPermissions } from './useWorkflowPermissions'

const CAN_I_ENDPOINT = '/authz/can_i' as const

vi.mock('../access/accessClient', () => ({
  accessFetchClient: { POST: vi.fn() },
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

function mockCanI(permissions: Record<string, boolean>) {
  vi.mocked(accessFetchClient.POST).mockImplementation(
    (_path: string, options?: { body?: { action?: string; resource_type?: string } }) => {
      const action = options?.body?.action
      const resource = options?.body?.resource_type
      const key = `${resource}:${action}`

      const mapping: Record<string, boolean> = {
        'workflow:create': permissions.create ?? true,
        'workflow:update': permissions.update ?? true,
        'workflow:delete': permissions.delete ?? true,
        'execution:run': permissions.run ?? true,
      }

      return Promise.resolve({ data: { allowed: mapping[key] ?? true } })
    }
  )
}

describe('useWorkflowPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses check_any_project for create and system-scoped update/delete/run without resourceProject', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)

    const { result } = renderHook(() => useWorkflowPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    expect(result.current.canRun).toBe(true)
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'workflow', check_any_project: true },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'update', resource_type: 'workflow' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'delete', resource_type: 'workflow' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'run', resource_type: 'execution' },
    })
  })

  it('scopes create/update/delete/run to resourceProject when provided', async () => {
    mockCanI({ create: true, update: true, delete: true, run: true })

    const { result } = renderHook(() => useWorkflowPermissions({ resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
    expect(result.current.canRun).toBe(true)
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'create', resource_type: 'workflow', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'update', resource_type: 'workflow', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'delete', resource_type: 'workflow', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith(CAN_I_ENDPOINT, {
      body: { action: 'run', resource_type: 'execution', resource_project: 'proj-1' },
    })
    const anyProjectCalls = (
      vi.mocked(accessFetchClient.POST).mock.calls as unknown as Array<
        [string, { body?: { check_any_project?: boolean } }]
      >
    ).filter(([, options]) => options.body?.check_any_project === true)
    expect(anyProjectCalls).toHaveLength(0)
  })

  it('returns canCreate false when workflow:create is denied', async () => {
    mockCanI({ create: false, update: true, delete: true, run: true })

    const { result } = renderHook(() => useWorkflowPermissions({ resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(true)
  })

  it('returns canRun false when execution:run is denied', async () => {
    mockCanI({ create: true, update: true, delete: true, run: false })

    const { result } = renderHook(() => useWorkflowPermissions({ resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canRun).toBe(false)
  })

  it('defaults to false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useWorkflowPermissions(), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.canRun).toBe(false)
  })

  it('provides tooltip messages for each permission', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useWorkflowPermissions(), { wrapper: createWrapper() })

    expect(result.current.tooltips.create).toContain('workflow:create')
    expect(result.current.tooltips.duplicate).toContain('duplicate this workflow')
    expect(result.current.tooltips.duplicate).toContain('workflow:create')
    expect(result.current.tooltips.update).toContain('workflow:update')
    expect(result.current.tooltips.delete).toContain('workflow:delete')
    expect(result.current.tooltips.run).toContain('execution:run')
  })
})
