import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useActiveAdminCount } from '../../hooks/useActiveAdminCount'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'
import { useAuthStore } from '../../stores/useAuthStore'
import { getUserIdFromToken } from '../../utils/jwtUtils'
import { accessClient } from '../access/accessClient'

import { logoutWithAlert } from './logoutWithAlert'
import { useAdminToggle } from './useAdminToggle'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: { useMutation: vi.fn() },
  accessFetchClient: { use: vi.fn() },
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

const mockShowAlert = vi.fn()

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({ showAlert: mockShowAlert }),
}))

const mockMutate = vi.fn()
const mockErrorHandler = vi.fn().mockReturnValue(vi.fn())
const mockLogout = vi.fn().mockResolvedValue(undefined)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupMocks({
  currentUserId = 'current-user',
  activeAdminCount = 2,
}: { currentUserId?: string | null; activeAdminCount?: number } = {}) {
  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
  })
  vi.mocked(useActiveAdminCount).mockReturnValue(activeAdminCount)
  vi.mocked(useMutationErrorHandler).mockReturnValue(mockErrorHandler)
  vi.mocked(useAuthStore).mockImplementation((selector: unknown) =>
    (selector as (s: { accessToken: string | null; logout: () => Promise<void> }) => unknown)({
      accessToken: 'mock-token',
      logout: mockLogout,
    })
  )
  vi.mocked(getUserIdFromToken).mockReturnValue(currentUserId)
}

const enabledAdmin = { id: 'admin-id', is_enabled: true }
const disabledAdmin = { id: 'admin-id', is_enabled: false }

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useAdminToggle', () => {
  const refetch = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
  })

  it('returns canToggle=false when user is not self even with multiple admins', () => {
    vi.mocked(getUserIdFromToken).mockReturnValue('other-user')

    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    expect(result.current.canToggle).toBe(false)
  })

  it('returns canToggle=true when admin is currently disabled (anyone can re-enable)', () => {
    vi.mocked(getUserIdFromToken).mockReturnValue('other-user')

    const { result } = renderHook(() => useAdminToggle(disabledAdmin, refetch))

    expect(result.current.canToggle).toBe(true)
  })

  it('returns canToggle=true when self and multiple admins exist', () => {
    vi.mocked(getUserIdFromToken).mockReturnValue('admin-id')
    vi.mocked(useActiveAdminCount).mockReturnValue(2)

    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    expect(result.current.canToggle).toBe(true)
  })

  it('returns canToggle=false when self but sole admin', () => {
    vi.mocked(getUserIdFromToken).mockReturnValue('admin-id')
    vi.mocked(useActiveAdminCount).mockReturnValue(1)

    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    expect(result.current.canToggle).toBe(false)
  })

  it('calls updateUser when enabling via handleToggle', () => {
    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    act(() => {
      result.current.handleToggle(true)
    })

    expect(mockMutate).toHaveBeenCalledTimes(1)
    expect(mockMutate.mock.calls[0][0]).toEqual({
      params: { path: { user_id: 'admin-id' } },
      body: { is_enabled: true },
    })
  })

  it('shows confirmation dialog instead of toggling when disabling', () => {
    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    act(() => {
      result.current.handleToggle(false)
    })

    expect(mockMutate).not.toHaveBeenCalled()
    expect(result.current.showConfirm).toBe(true)
  })

  it('calls updateUser with is_enabled=false on confirmDisable', () => {
    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    act(() => {
      result.current.handleToggle(false)
    })
    act(() => {
      result.current.confirmDisable()
    })

    expect(result.current.showConfirm).toBe(false)
    expect(mockMutate).toHaveBeenCalledTimes(1)
    expect(mockMutate.mock.calls[0][0]).toEqual({
      params: { path: { user_id: 'admin-id' } },
      body: { is_enabled: false },
    })
  })

  it('closes confirmation dialog on cancelDisable', () => {
    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    act(() => {
      result.current.handleToggle(false)
    })
    expect(result.current.showConfirm).toBe(true)

    act(() => {
      result.current.cancelDisable()
    })
    expect(result.current.showConfirm).toBe(false)
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('does not call updateUser when builtinUser is undefined', () => {
    const { result } = renderHook(() => useAdminToggle(undefined, refetch))

    act(() => {
      result.current.handleToggle(true)
    })

    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('calls refetch on successful enable', () => {
    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    act(() => {
      result.current.handleToggle(true)
    })

    const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => {
      callbacks.onSuccess()
    })

    expect(refetch).toHaveBeenCalled()
  })

  it('calls logout via detachPromise when disable succeeds', () => {
    const { result } = renderHook(() => useAdminToggle(enabledAdmin, refetch))

    act(() => {
      result.current.handleToggle(false)
    })
    act(() => {
      result.current.confirmDisable()
    })

    const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => {
      callbacks.onSuccess()
    })

    expect(logoutWithAlert).toHaveBeenCalledWith(mockLogout, mockShowAlert, 'Administrator disabled — signing out')
    expect(refetch).not.toHaveBeenCalled()
  })
})
