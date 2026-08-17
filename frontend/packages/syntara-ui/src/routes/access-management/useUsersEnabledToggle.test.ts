import type { User } from '@syntara/contracts'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useActiveAdminCount } from '../../hooks/useActiveAdminCount'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'
import { useAuthStore } from '../../stores/useAuthStore'
import { getUserIdFromToken } from '../../utils/jwtUtils'
import { accessClient } from '../access/accessClient'

import { LAST_ADMIN_TOGGLE_DISABLED_REASON } from './adminConstants'
import { logoutWithAlert } from './logoutWithAlert'
import { useUserPermissions } from './useUserPermissions'
import { useUsersEnabledToggle } from './useUsersEnabledToggle'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useMutation: vi.fn(),
    useQuery: vi.fn(),
  },
}))

vi.mock('../../hooks/useActiveAdminCount', () => ({
  useActiveAdminCount: vi.fn(),
}))

vi.mock('../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: vi.fn(),
}))

vi.mock('../../stores/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}))

vi.mock('../../utils/jwtUtils', () => ({
  getUserIdFromToken: vi.fn(),
}))

vi.mock('./logoutWithAlert', () => ({
  logoutWithAlert: vi.fn(),
}))

vi.mock('./useUserPermissions', () => ({
  useUserPermissions: vi.fn(),
}))

const mockShowAlert = vi.fn()

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({ showAlert: mockShowAlert }),
}))

const mockMutateAsync = vi.fn()
const mockErrorHandler = vi.fn().mockReturnValue(vi.fn())
const mockLogout = vi.fn().mockResolvedValue(undefined)
const mockRefetch = vi.fn().mockResolvedValue(undefined)

function makeUser(overrides: Partial<User> & Pick<User, 'id' | 'username' | 'is_enabled'>): User {
  return {
    email: `${overrides.username}@example.com`,
    first_name: 'Test',
    last_name: 'User',
    auth_type: 'local',
    auth_sources: ['Local'],
    is_builtin: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

function setupMocks({
  currentUserId = 'viewer-id',
  activeAdminCount = 2,
  adminMembers = [{ id: 'admin-id', is_enabled: true }],
  canUpdate = true,
}: {
  currentUserId?: string | null
  activeAdminCount?: number
  adminMembers?: { id: string; is_enabled: boolean }[]
  canUpdate?: boolean
} = {}) {
  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutateAsync: mockMutateAsync,
    mutate: vi.fn(),
    isPending: false,
  } as never)
  vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
    const endpoint = args[1] as string
    if (endpoint === '/groups') {
      return {
        data: { resources: [{ id: 'admins-group', name: 'admins', is_builtin: true }] },
      } as never
    }
    if (endpoint === '/groups/{group_id}/members') {
      return {
        data: { resources: adminMembers },
      } as never
    }
    return { data: undefined } as never
  })
  vi.mocked(useActiveAdminCount).mockReturnValue(activeAdminCount)
  vi.mocked(useMutationErrorHandler).mockReturnValue(mockErrorHandler)
  mockErrorHandler.mockReturnValue(vi.fn())
  vi.mocked(useAuthStore).mockImplementation((selector: unknown) =>
    (selector as (s: { accessToken: string | null; logout: () => Promise<void> }) => unknown)({
      accessToken: 'mock-token',
      logout: mockLogout,
    })
  )
  vi.mocked(getUserIdFromToken).mockReturnValue(currentUserId)
  vi.mocked(useUserPermissions).mockReturnValue({
    canCreate: true,
    canUpdate,
    canDelete: true,
    canRevoke: true,
    isLoading: false,
    tooltips: {
      create: 'create tip',
      update: 'update tip',
      delete: 'delete tip',
      revoke: 'revoke tip',
    },
  })
}

describe('useUsersEnabledToggle', () => {
  const adminUser = makeUser({ id: 'admin-id', username: 'admin', is_enabled: true, is_builtin: true })
  const jdoeUser = makeUser({ id: 'jdoe-id', username: 'jdoe', is_enabled: true })
  const viewerUser = makeUser({ id: 'viewer-id', username: 'viewer1', is_enabled: false })
  const users = [adminUser, jdoeUser, viewerUser]

  beforeEach(() => {
    vi.clearAllMocks()
    mockMutateAsync.mockResolvedValue({})
    setupMocks()
  })

  it('returns permission tooltip when update is not allowed', () => {
    setupMocks({ canUpdate: false })
    const { result } = renderHook(() => useUsersEnabledToggle(users, mockRefetch))

    expect(result.current.getToggleDisabledReason(jdoeUser)).toBe('update tip')
  })

  it('blocks disabling the last enabled admin', () => {
    setupMocks({ activeAdminCount: 1, adminMembers: [{ id: 'jdoe-id', is_enabled: true }] })
    const { result } = renderHook(() => useUsersEnabledToggle(users, mockRefetch))

    expect(result.current.getToggleDisabledReason(jdoeUser)).toBe(LAST_ADMIN_TOGGLE_DISABLED_REASON)
  })

  it('opens disable confirmation instead of patching immediately', () => {
    const { result } = renderHook(() => useUsersEnabledToggle(users, mockRefetch))

    act(() => {
      result.current.handleToggleEnabled(jdoeUser)
    })

    expect(result.current.disableConfirm.isOpen).toBe(true)
    expect(result.current.disableConfirm.user?.id).toBe('jdoe-id')
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('enables a disabled user immediately with optimistic state', async () => {
    const { result } = renderHook(() => useUsersEnabledToggle(users, mockRefetch))

    act(() => {
      result.current.handleToggleEnabled(viewerUser)
    })

    await waitFor(() => {
      expect(result.current.users.find((u) => u.id === 'viewer-id')?.is_enabled).toBe(true)
    })
    expect(mockMutateAsync).toHaveBeenCalledWith({
      params: { path: { user_id: 'viewer-id' } },
      body: { is_enabled: true },
    })
    await waitFor(() => {
      expect(mockShowAlert).toHaveBeenCalledWith({
        title: 'User enabled',
        variant: 'success',
        autoDismiss: true,
      })
    })
    expect(mockRefetch).toHaveBeenCalled()
  })

  it('logs out when confirming self-disable', async () => {
    setupMocks({ currentUserId: 'jdoe-id' })
    const { result } = renderHook(() => useUsersEnabledToggle(users, mockRefetch))

    act(() => {
      result.current.handleToggleEnabled(jdoeUser)
    })
    act(() => {
      result.current.disableConfirm.confirm()
    })

    await waitFor(() => {
      expect(logoutWithAlert).toHaveBeenCalledWith(mockLogout, mockShowAlert, 'Account disabled — signing out')
    })
    expect(mockRefetch).not.toHaveBeenCalled()
  })

  it('patches is_enabled=false after confirming disable for another user', async () => {
    const { result } = renderHook(() => useUsersEnabledToggle(users, mockRefetch))

    act(() => {
      result.current.handleToggleEnabled(jdoeUser)
    })
    act(() => {
      result.current.disableConfirm.confirm()
    })

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        params: { path: { user_id: 'jdoe-id' } },
        body: { is_enabled: false },
      })
    })
    await waitFor(() => {
      expect(mockShowAlert).toHaveBeenCalledWith({
        title: 'User disabled',
        variant: 'success',
        autoDismiss: true,
      })
    })
  })

  it('reports mutation errors through the shared handler', async () => {
    const error = new Error('boom')
    mockMutateAsync.mockRejectedValue(error)
    const { result } = renderHook(() => useUsersEnabledToggle(users, mockRefetch))

    act(() => {
      result.current.handleToggleEnabled(viewerUser)
    })

    await waitFor(() => {
      expect(mockErrorHandler).toHaveBeenCalledWith({ title: 'Failed to enable user' })
    })
  })
})
