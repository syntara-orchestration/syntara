import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { adminClient } from '../../client'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'

import { useRevokeUserTokens } from './useRevokeUserTokens'

vi.mock('../../client', () => ({
  adminClient: { useMutation: vi.fn() },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: vi.fn(),
}))

const mockShowSuccess = vi.fn()

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({ showSuccess: mockShowSuccess }),
}))

const mockMutate = vi.fn()
const mockErrorHandler = vi.fn().mockReturnValue(vi.fn())

function setupMocks() {
  vi.mocked(adminClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
  })
  vi.mocked(useMutationErrorHandler).mockReturnValue(mockErrorHandler)
}

const testUser = {
  id: 'user-1',
  username: 'alice',
  first_name: 'Alice',
  last_name: 'Smith',
  full_name: 'Alice Smith',
  is_enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('useRevokeUserTokens', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
  })

  it('initializes with dialog closed', () => {
    const { result } = renderHook(() => useRevokeUserTokens())

    expect(result.current.revokeDialog.isOpen).toBe(false)
    expect(result.current.revokeDialog.item).toBeNull()
  })

  it('opens the dialog with the provided user', () => {
    const { result } = renderHook(() => useRevokeUserTokens())

    act(() => {
      result.current.revokeDialog.open(testUser)
    })

    expect(result.current.revokeDialog.isOpen).toBe(true)
    expect(result.current.revokeDialog.item).toEqual(testUser)
  })

  it('does nothing when handleRevoke is called with no dialog item', () => {
    const { result } = renderHook(() => useRevokeUserTokens())

    act(() => {
      result.current.handleRevoke()
    })

    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('calls revokeUserTokens mutation with the correct username', () => {
    const { result } = renderHook(() => useRevokeUserTokens())

    act(() => {
      result.current.revokeDialog.open(testUser)
    })
    act(() => {
      result.current.handleRevoke()
    })

    expect(mockMutate).toHaveBeenCalledTimes(1)
    expect(mockMutate.mock.calls[0][0]).toEqual({
      params: { path: { username: 'alice' } },
    })
  })

  it('shows success alert and closes dialog on success', () => {
    const { result } = renderHook(() => useRevokeUserTokens())

    act(() => {
      result.current.revokeDialog.open(testUser)
    })
    act(() => {
      result.current.handleRevoke()
    })

    const callbacks = mockMutate.mock.calls[0][1] as {
      onSuccess: (data: { message: string }) => void
      onSettled: () => void
    }

    act(() => {
      callbacks.onSuccess({ message: 'All tokens revoked for alice' })
    })

    expect(mockShowSuccess).toHaveBeenCalledWith({
      title: 'Tokens revoked',
      description: 'All tokens revoked for alice',
    })

    act(() => {
      callbacks.onSettled()
    })

    expect(result.current.revokeDialog.isOpen).toBe(false)
  })

  it('uses mutation error handler on error', () => {
    const onErrorFn = vi.fn()
    mockErrorHandler.mockReturnValue(onErrorFn)

    const { result } = renderHook(() => useRevokeUserTokens())

    act(() => {
      result.current.revokeDialog.open(testUser)
    })
    act(() => {
      result.current.handleRevoke()
    })

    expect(mockErrorHandler).toHaveBeenCalledWith({
      title: 'Failed to revoke tokens',
      context: 'User "alice"',
    })

    const callbacks = mockMutate.mock.calls[0][1] as { onError: typeof onErrorFn }
    expect(callbacks.onError).toBe(onErrorFn)
  })

  it('closes the dialog via onSettled regardless of outcome', () => {
    const { result } = renderHook(() => useRevokeUserTokens())

    act(() => {
      result.current.revokeDialog.open(testUser)
    })
    act(() => {
      result.current.handleRevoke()
    })

    const callbacks = mockMutate.mock.calls[0][1] as { onSettled: () => void }
    act(() => {
      callbacks.onSettled()
    })

    expect(result.current.revokeDialog.isOpen).toBe(false)
  })
})
