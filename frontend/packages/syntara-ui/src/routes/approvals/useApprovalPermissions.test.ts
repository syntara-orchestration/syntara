import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { mockAuthMiddleware } from '../../test/mockAuthMiddleware'
import { accessFetchClient } from '../access/accessClient'
import { useAllPermissions } from '../access/useAllPermissions'

import { useApprovalPermissions } from './useApprovalPermissions'

vi.mock('../access/accessClient', () => ({
  accessFetchClient: { POST: vi.fn() },
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../access/useAllPermissions', () => ({
  useAllPermissions: vi.fn(() => ({
    permissions: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })),
}))

vi.mock('../../client', () => ({
  authMiddleware: mockAuthMiddleware,
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
        'approval:read': permissions.read ?? true,
        'approval:decide': permissions.decide ?? true,
      }

      return Promise.resolve({ data: { allowed: mapping[key] ?? true } })
    }
  )
}

function mockProjectPermissions(
  perms: { effect?: string; actions: string[]; scope?: string; project?: string; policy_name?: string }[]
) {
  vi.mocked(useAllPermissions).mockReturnValue({
    permissions: perms.map((p) => ({ policy_name: 'test', ...p })) as ReturnType<
      typeof useAllPermissions
    >['permissions'],
    isLoading: false,
    error: null,
    refetch: vi.fn() as ReturnType<typeof useAllPermissions>['refetch'],
  })
}

describe('useApprovalPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns all permissions as true when granted', async () => {
    mockCanI({ read: true, decide: true })

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(true)
    expect(result.current.canDecide).toBe(true)
    expect(result.current.isError).toBe(false)
  })

  it('returns isError when loading project permissions fails', async () => {
    mockCanI({ read: true, decide: true })
    vi.mocked(useAllPermissions).mockReturnValue({
      permissions: [],
      isLoading: false,
      error: new Error('Failed to load permissions'),
      refetch: vi.fn() as ReturnType<typeof useAllPermissions>['refetch'],
    })

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.isError).toBe(true)
  })

  it('returns canRead false when approval:read is denied', async () => {
    mockCanI({ read: false, decide: true })

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(false)
    expect(result.current.canDecide).toBe(true)
  })

  it('returns canDecide false when approval:decide is denied', async () => {
    mockCanI({ read: true, decide: false })

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(true)
    expect(result.current.canDecide).toBe(false)
  })

  it('returns all permissions false when all denied', async () => {
    mockCanI({ read: false, decide: false })

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(false)
    expect(result.current.canDecide).toBe(false)
  })

  it('defaults to false while loading (safe-false)', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    expect(result.current.isChecking).toBe(true)
    expect(result.current.canRead).toBe(false)
    expect(result.current.canDecide).toBe(false)
  })

  it('defaults to false on error (safe-false)', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(false)
    expect(result.current.canDecide).toBe(false)
  })

  it('provides tooltip message for decide permission', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

    expect(result.current.tooltips.decide).toContain('approval:decide')
    expect(result.current.tooltips.decide).toContain('decide on approvals')
  })

  it('returns canDecide true when user has project-scoped permission for the given projectId', async () => {
    // Global decide is denied, but user has project-scoped permission for 'Project Alpha'
    mockCanI({ read: true, decide: false })

    mockProjectPermissions([
      { effect: 'allow', actions: ['approval:decide'], scope: 'project', project: 'Project Alpha' },
    ])

    const { result } = renderHook(() => useApprovalPermissions('Project Alpha'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(true)
    expect(result.current.canDecide).toBe(true) // Should be true for this project
  })

  it('returns canDecide false when user lacks project-scoped permission for the given projectId', async () => {
    // Global decide is denied, user has project-scoped permission for 'Project Alpha' but not 'Project Beta'
    mockCanI({ read: true, decide: false })

    mockProjectPermissions([
      { effect: 'allow', actions: ['approval:decide'], scope: 'project', project: 'Project Alpha' },
    ])

    const { result } = renderHook(() => useApprovalPermissions('Project Beta'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(true)
    expect(result.current.canDecide).toBe(false) // Should be false for this project
  })

  it('returns canDecide based on global permission when projectId is null', async () => {
    mockCanI({ read: true, decide: true })

    const { result } = renderHook(() => useApprovalPermissions(null), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canRead).toBe(true)
    expect(result.current.canDecide).toBe(true) // Should use global permission
  })

  describe('project-scoped approval:read', () => {
    it('returns canRead true when global read is denied but user has project-scoped read for the given projectId', async () => {
      mockCanI({ read: false, decide: false })

      mockProjectPermissions([
        { effect: 'allow', actions: ['approval:read'], scope: 'project', project: 'Project Alpha' },
      ])

      const { result } = renderHook(() => useApprovalPermissions('Project Alpha'), { wrapper: createWrapper() })

      await waitFor(() => {
        expect(result.current.isChecking).toBe(false)
      })

      expect(result.current.canRead).toBe(true)
      expect(result.current.canDecide).toBe(false)
    })

    it('returns canRead false when global read is denied and user has project-scoped read for a different project', async () => {
      mockCanI({ read: false, decide: false })

      mockProjectPermissions([
        { effect: 'allow', actions: ['approval:read'], scope: 'project', project: 'Project Alpha' },
      ])

      const { result } = renderHook(() => useApprovalPermissions('Project Beta'), { wrapper: createWrapper() })

      await waitFor(() => {
        expect(result.current.isChecking).toBe(false)
      })

      expect(result.current.canRead).toBe(false)
    })

    it('returns canRead true on list page (no projectId) when user has any project-scoped read', async () => {
      mockCanI({ read: false, decide: false })

      mockProjectPermissions([
        { effect: 'allow', actions: ['approval:read'], scope: 'project', project: 'Project Alpha' },
      ])

      const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

      await waitFor(() => {
        expect(result.current.isChecking).toBe(false)
      })

      expect(result.current.canRead).toBe(true)
    })

    it('defers to can_i for system-level read (what_can_i system-scope alone does not grant canRead)', async () => {
      mockCanI({ read: false, decide: false })

      mockProjectPermissions([{ effect: 'allow', actions: ['approval:read'], scope: 'system' }])

      const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

      await waitFor(() => {
        expect(result.current.isChecking).toBe(false)
      })

      expect(result.current.canRead).toBe(false)
    })

    it('defers to can_i for system-level decide (what_can_i system-scope alone does not grant canDecide)', async () => {
      mockCanI({ read: false, decide: false })

      mockProjectPermissions([{ effect: 'allow', actions: ['approval:decide'], scope: 'system' }])

      const { result } = renderHook(() => useApprovalPermissions(), { wrapper: createWrapper() })

      await waitFor(() => {
        expect(result.current.isChecking).toBe(false)
      })

      expect(result.current.canDecide).toBe(false)
    })
  })
})
