import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useMutationErrorHandler } from './useMutationErrorHandler'

// Mock useAlerts
const mockShowAlert = vi.fn()
vi.mock('../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({
    showAlert: mockShowAlert,
  }),
}))

describe('useMutationErrorHandler', () => {
  beforeEach(() => {
    mockShowAlert.mockClear()
  })

  it('shows danger alert for regular errors', () => {
    const { result } = renderHook(() => useMutationErrorHandler())

    const handler = result.current({ title: 'Test Error' })
    handler({ detail: 'Something went wrong' })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'danger',
        title: 'Test Error',
        description: 'Something went wrong',
      })
    )
  })

  it('shows warning alert for 503 errors', () => {
    const { result } = renderHook(() => useMutationErrorHandler())

    const handler = result.current({ title: 'Service Error' })
    handler({ status: 503, detail: 'Service unavailable' })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'warning',
        title: 'Service Error',
        description: 'Service unavailable',
      })
    )
  })

  it('calls on503 callback for 503 errors', () => {
    const on503 = vi.fn()
    const { result } = renderHook(() => useMutationErrorHandler())

    const handler = result.current({ on503 })
    handler({ status: 503, detail: 'Service unavailable' })

    expect(on503).toHaveBeenCalled()
  })

  it('calls onRetryable callback for retryable errors', () => {
    const onRetryable = vi.fn()
    const { result } = renderHook(() => useMutationErrorHandler())

    const handler = result.current({ onRetryable })
    handler({ status: 500, retryable: true, detail: 'Server error' })

    expect(onRetryable).toHaveBeenCalled()
  })

  it('includes context in error message', () => {
    const { result } = renderHook(() => useMutationErrorHandler())

    const handler = result.current({ title: 'Error', context: 'Creating workflow' })
    handler({ detail: 'Failed' })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Creating workflow: Failed',
      })
    )
  })

  it('uses error title when no custom title provided', () => {
    const { result } = renderHook(() => useMutationErrorHandler())

    const handler = result.current({})
    handler({ title: 'Validation Error', detail: 'Field required' })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Validation Error',
      })
    )
  })

  it('sets autoDismiss false for validation errors by default', () => {
    const { result } = renderHook(() => useMutationErrorHandler())

    const handler = result.current({})
    handler({ status: 422, detail: [{ loc: ['body', 'name'], msg: 'required' }] })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        autoDismiss: false,
      })
    )
  })

  it('respects persist option override', () => {
    const { result } = renderHook(() => useMutationErrorHandler())

    // Force auto-dismiss even for validation errors
    const handler = result.current({ persist: false })
    handler({ status: 422, detail: [{ loc: ['body', 'name'], msg: 'required' }] })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        autoDismiss: true,
      })
    )
  })
})
