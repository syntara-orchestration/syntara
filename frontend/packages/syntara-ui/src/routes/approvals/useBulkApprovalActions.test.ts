import { renderHook, waitFor } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useBulkApprovalActions } from './useBulkApprovalActions'

// Type for batch approval response
type BatchApprovalResponse = {
  total_success: number
  total_failed: number
  results: unknown[]
}

// Type for mutation callbacks
type MutationCallbacks = {
  onSuccess: (response: BatchApprovalResponse) => void
  onError: (error: Error) => void
  onSettled: () => void
}

// Mock the approvalsClient
vi.mock('../../client', () => ({
  approvalsClient: {
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// Mock the alerts provider
const mockShowAlert = vi.fn()
const mockShowSuccess = vi.fn()
vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showAlert: mockShowAlert, showSuccess: mockShowSuccess }),
}))

// Mock the mutation error handler
const mockHandleError = vi.fn()
vi.mock('../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: () => {
    return (options: { title?: string }) => {
      return (error: unknown) => {
        mockHandleError({ title: options.title, error })
      }
    }
  },
}))

describe('useBulkApprovalActions', () => {
  const mockApprovalIds = new Set(['approval-1', 'approval-2'])

  const mockOnSuccess = vi.fn()
  let mockMutate: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    vi.clearAllMocks()
    mockHandleError.mockClear()
    mockMutate = vi.fn()

    const { approvalsClient } = await import('../../client')
    vi.mocked(approvalsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isSuccess: false,
      isError: false,
      data: undefined,
      error: null,
      reset: vi.fn(),
      mutateAsync: vi.fn(),
      variables: undefined,
      context: undefined,
      failureCount: 0,
      failureReason: null,
      isIdle: true,
      isPaused: false,
      status: 'idle',
      submittedAt: 0,
    })
  })

  it('initializes with closed dialogs', () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    expect(result.current.bulkApproveDialogOpen).toBe(false)
    expect(result.current.bulkRejectDialogOpen).toBe(false)
  })

  it('opens approve dialog', () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.setBulkApproveDialogOpen(true)
    })

    expect(result.current.bulkApproveDialogOpen).toBe(true)
  })

  it('opens reject dialog', () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.setBulkRejectDialogOpen(true)
    })

    expect(result.current.bulkRejectDialogOpen).toBe(true)
  })

  it('handles bulk approve with note', () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkApprove('Test note')
    })

    expect(mockMutate).toHaveBeenCalledWith(
      {
        body: {
          decisions: [
            { approval_id: 'approval-1', status: 'approved', notes: 'Test note' },
            { approval_id: 'approval-2', status: 'approved', notes: 'Test note' },
          ],
        },
      },
      expect.objectContaining({
        onSuccess: expect.any(Function) as MutationCallbacks['onSuccess'],
        onError: expect.any(Function) as MutationCallbacks['onError'],
        onSettled: expect.any(Function) as MutationCallbacks['onSettled'],
      }) as MutationCallbacks
    )
  })

  it('handles bulk approve without note', () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkApprove(null)
    })

    expect(mockMutate).toHaveBeenCalledWith(
      {
        body: {
          decisions: [
            { approval_id: 'approval-1', status: 'approved', notes: null },
            { approval_id: 'approval-2', status: 'approved', notes: null },
          ],
        },
      },
      expect.any(Object)
    )
  })

  it('handles bulk reject with note', () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkReject('Rejection reason')
    })

    expect(mockMutate).toHaveBeenCalledWith(
      {
        body: {
          decisions: [
            { approval_id: 'approval-1', status: 'rejected', notes: 'Rejection reason' },
            { approval_id: 'approval-2', status: 'rejected', notes: 'Rejection reason' },
          ],
        },
      },
      expect.any(Object)
    )
  })

  it('calls onSuccess and shows success alert when all approvals succeed', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkApprove('Test note')
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    act(() => {
      callbacks.onSuccess({ total_success: 2, total_failed: 0, results: [] })
    })

    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalledTimes(1)
      expect(mockShowSuccess).toHaveBeenCalledWith({
        title: 'Approvals submitted',
        description: 'Successfully approved 2 approvals.',
      })
    })
  })

  it('shows singular message for single approval success', async () => {
    const singleApprovalId = new Set(['approval-1'])
    const { result } = renderHook(() => useBulkApprovalActions(singleApprovalId, mockOnSuccess))

    act(() => {
      result.current.handleBulkApprove(null)
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    act(() => {
      callbacks.onSuccess({ total_success: 1, total_failed: 0, results: [] })
    })

    await waitFor(() => {
      expect(mockShowSuccess).toHaveBeenCalledWith({
        title: 'Approvals submitted',
        description: 'Successfully approved 1 approval.',
      })
    })
  })

  it('shows warning alert for partial success', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkApprove(null)
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    act(() => {
      callbacks.onSuccess({ total_success: 1, total_failed: 1, results: [] })
    })

    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalledTimes(1)
      expect(mockShowAlert).toHaveBeenCalledWith({
        title: 'Partial success',
        description: 'Approved 1 approval, but 1 failed. Check the list and try again.',
        variant: 'warning',
        autoDismiss: false,
      })
    })
  })

  it('shows error alert on mutation failure', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkApprove(null)
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    const error = new Error('Network error')

    act(() => {
      callbacks.onError(error)
    })

    await waitFor(() => {
      expect(mockHandleError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Bulk approval failed', error }))
    })
  })

  it('closes approve dialog on success', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.setBulkApproveDialogOpen(true)
    })

    expect(result.current.bulkApproveDialogOpen).toBe(true)

    act(() => {
      result.current.handleBulkApprove(null)
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    act(() => {
      callbacks.onSuccess({ total_success: 2, total_failed: 0, results: [] })
    })

    await waitFor(() => {
      expect(result.current.bulkApproveDialogOpen).toBe(false)
    })
  })

  it('closes approve dialog on error (via onSettled)', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.setBulkApproveDialogOpen(true)
    })

    act(() => {
      result.current.handleBulkApprove(null)
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    act(() => {
      callbacks.onSettled()
    })

    await waitFor(() => {
      expect(result.current.bulkApproveDialogOpen).toBe(false)
    })
  })

  it('handles reject success with correct alert', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkReject('Test reason')
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    act(() => {
      callbacks.onSuccess({ total_success: 2, total_failed: 0, results: [] })
    })

    await waitFor(() => {
      expect(mockShowSuccess).toHaveBeenCalledWith({
        title: 'Approvals rejected',
        description: 'Successfully rejected 2 approvals.',
      })
    })
  })

  it('closes reject dialog on success', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.setBulkRejectDialogOpen(true)
    })

    expect(result.current.bulkRejectDialogOpen).toBe(true)

    act(() => {
      result.current.handleBulkReject('Test reason')
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    act(() => {
      callbacks.onSuccess({ total_success: 2, total_failed: 0, results: [] })
    })

    await waitFor(() => {
      expect(result.current.bulkRejectDialogOpen).toBe(false)
    })
  })

  it('shows error alert for reject failure', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkReject('Test reason')
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    const error = new Error('Server error')

    act(() => {
      callbacks.onError(error)
    })

    await waitFor(() => {
      expect(mockHandleError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Bulk rejection failed', error }))
    })
  })

  it('handles unknown error type', async () => {
    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    act(() => {
      result.current.handleBulkApprove(null)
    })

    const mutateCall = mockMutate.mock.calls[0] as [unknown, MutationCallbacks]
    const callbacks = mutateCall[1]

    const error = 'Unknown error'

    act(() => {
      callbacks.onError(error as unknown as Error)
    })

    await waitFor(() => {
      expect(mockHandleError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Bulk approval failed', error }))
    })
  })

  it('exposes isPending from mutation', async () => {
    const { approvalsClient } = await import('../../client')
    vi.mocked(approvalsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
      isSuccess: false,
      isError: false,
      data: undefined,
      error: null,
      reset: vi.fn(),
      mutateAsync: vi.fn(),
      variables: undefined,
      context: undefined,
      failureCount: 0,
      failureReason: null,
      isIdle: false,
      isPaused: false,
      status: 'pending',
      submittedAt: Date.now(),
    })

    const { result } = renderHook(() => useBulkApprovalActions(mockApprovalIds, mockOnSuccess))

    expect(result.current.isPending).toBe(true)
  })
})
