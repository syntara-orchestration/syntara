import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCanApprovalAction } from './useCanApprovalAction'

// Mock the access client
const mockPost = vi.fn()
vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessFetchClient: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-return, @typescript-eslint/no-unsafe-argument
    POST: (...args: any[]) => mockPost(...args),
  },
}))

describe('useCanApprovalAction', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('initializes with isChecking true and canPerformAction false', () => {
    mockPost.mockReturnValue(
      new Promise(() => {
        // Never resolves
      })
    )

    const { result } = renderHook(() => useCanApprovalAction('decide'))

    expect(result.current.isChecking).toBe(true)
    expect(result.current.canPerformAction).toBe(false)
  })

  it('checks approval:decide permission at system level', async () => {
    mockPost.mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useCanApprovalAction('decide'))

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
      body: {
        action: 'decide',
        resource_type: 'approval',
      },
    })
    expect(result.current.canPerformAction).toBe(true)
  })

  it('checks approval:read permission at system level', async () => {
    mockPost.mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useCanApprovalAction('read'))

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
      body: {
        action: 'read',
        resource_type: 'approval',
      },
    })
    expect(result.current.canPerformAction).toBe(true)
  })

  it('checks approval:decide permission scoped to a project', async () => {
    mockPost.mockResolvedValue({ data: { allowed: false } })

    const { result } = renderHook(() => useCanApprovalAction('decide', 'project-123'))

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
      body: {
        action: 'decide',
        resource_type: 'approval',
        resource_id: 'project:project-123',
      },
    })
    expect(result.current.canPerformAction).toBe(false)
  })

  it('sets canPerformAction to false when API returns allowed:false', async () => {
    mockPost.mockResolvedValue({ data: { allowed: false } })

    const { result } = renderHook(() => useCanApprovalAction('decide'))

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canPerformAction).toBe(false)
  })

  it('handles API errors gracefully', async () => {
    mockPost.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useCanApprovalAction('decide'))

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    // Should default to false on error
    expect(result.current.canPerformAction).toBe(false)
  })

  it('handles missing data gracefully', async () => {
    mockPost.mockResolvedValue({ data: null })

    const { result } = renderHook(() => useCanApprovalAction('decide'))

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.canPerformAction).toBe(false)
  })

  it('cancels in-flight requests on unmount', async () => {
    let resolveFn: ((value: unknown) => void) | null = null
    const pendingPromise = new Promise((resolve) => {
      resolveFn = resolve
    })
    mockPost.mockReturnValue(pendingPromise)

    const { result, unmount } = renderHook(() => useCanApprovalAction('decide'))

    expect(result.current.isChecking).toBe(true)

    unmount()

    // Resolve after unmount
    resolveFn!({ data: { allowed: true } })

    await new Promise((resolve) => setTimeout(resolve, 10))

    // State should not have been updated after unmount
    expect(result.current.isChecking).toBe(true)
    expect(result.current.canPerformAction).toBe(false)
  })

  it('re-checks permission when action changes', async () => {
    mockPost.mockResolvedValue({ data: { allowed: true } })

    type ActionProps = { action: 'decide' | 'read' }
    const { result, rerender } = renderHook(({ action }: ActionProps) => useCanApprovalAction(action), {
      initialProps: { action: 'decide' },
    })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
      body: {
        action: 'decide',
        resource_type: 'approval',
      },
    })

    // Change action
    mockPost.mockClear()
    mockPost.mockResolvedValue({ data: { allowed: false } })
    rerender({ action: 'read' })

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
        body: {
          action: 'read',
          resource_type: 'approval',
        },
      })
    })

    expect(mockPost).toHaveBeenCalledTimes(1)
  })

  it('re-checks permission when projectId changes', async () => {
    mockPost.mockResolvedValue({ data: { allowed: true } })

    const { result, rerender } = renderHook(({ projectId }) => useCanApprovalAction('decide', projectId), {
      initialProps: { projectId: 'project-1' },
    })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
      body: {
        action: 'decide',
        resource_type: 'approval',
        resource_id: 'project:project-1',
      },
    })

    // Change project
    mockPost.mockClear()
    mockPost.mockResolvedValue({ data: { allowed: false } })
    rerender({ projectId: 'project-2' })

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
        body: {
          action: 'decide',
          resource_type: 'approval',
          resource_id: 'project:project-2',
        },
      })
    })

    expect(mockPost).toHaveBeenCalledTimes(1)
  })

  it('handles projectId being null', async () => {
    mockPost.mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useCanApprovalAction('decide', null))

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(mockPost).toHaveBeenCalledWith('/authz/can_i', {
      body: {
        action: 'decide',
        resource_type: 'approval',
      },
    })
  })
})
