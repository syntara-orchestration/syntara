import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useApiErrorAlert } from './useApiErrorAlert'

// Mock useAlerts
const mockShowError = vi.fn()
const mockShowWarning = vi.fn()
vi.mock('../providers/alerts', () => ({
  useAlerts: () => ({
    showError: mockShowError,
    showWarning: mockShowWarning,
  }),
}))

describe('useApiErrorAlert', () => {
  beforeEach(() => {
    mockShowError.mockClear()
    mockShowWarning.mockClear()
  })

  it('does nothing when error is null', () => {
    renderHook(() => useApiErrorAlert(null))

    expect(mockShowError).not.toHaveBeenCalled()
    expect(mockShowWarning).not.toHaveBeenCalled()
  })

  it('does nothing when error is undefined', () => {
    renderHook(() => useApiErrorAlert(undefined))

    expect(mockShowError).not.toHaveBeenCalled()
    expect(mockShowWarning).not.toHaveBeenCalled()
  })

  it('shows error alert for regular errors', () => {
    renderHook(() => useApiErrorAlert({ detail: 'Something went wrong' }))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Error', description: 'Something went wrong' })
  })

  it('shows warning alert for 503 errors', () => {
    renderHook(() => useApiErrorAlert({ status: 503, detail: 'Service unavailable' }))

    expect(mockShowWarning).toHaveBeenCalledWith({ title: 'Error', description: 'Service unavailable' })
    expect(mockShowError).not.toHaveBeenCalled()
  })

  it('uses custom title when provided', () => {
    renderHook(() => useApiErrorAlert({ detail: 'Failed' }, { title: 'Custom Title' }))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Custom Title', description: 'Failed' })
  })

  it('includes context in message when provided', () => {
    renderHook(() => useApiErrorAlert({ detail: 'Failed' }, { context: 'Loading data' }))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Error', description: 'Loading data: Failed' })
  })

  it('suppresses 503 errors when suppress503 is true', () => {
    renderHook(() => useApiErrorAlert({ status: 503, detail: 'Service unavailable' }, { suppress503: true }))

    expect(mockShowWarning).not.toHaveBeenCalled()
    expect(mockShowError).not.toHaveBeenCalled()
  })

  it('suppresses 403 errors with status code', () => {
    renderHook(() => useApiErrorAlert({ status: 403, detail: 'Forbidden' }))

    expect(mockShowError).not.toHaveBeenCalled()
    expect(mockShowWarning).not.toHaveBeenCalled()
  })

  it('suppresses errors with "not authorized" in message (no status code)', () => {
    renderHook(() => useApiErrorAlert({ detail: 'Not authorized to perform read on setting' }))

    expect(mockShowError).not.toHaveBeenCalled()
    expect(mockShowWarning).not.toHaveBeenCalled()
  })

  it('dedupes repeated errors with same key', () => {
    const error = { detail: 'Same error' }
    const { rerender } = renderHook(({ e }) => useApiErrorAlert(e), {
      initialProps: { e: error },
    })

    expect(mockShowError).toHaveBeenCalledTimes(1)

    // Same error object reference
    rerender({ e: error })
    expect(mockShowError).toHaveBeenCalledTimes(1)
  })

  it('shows alert for different errors', () => {
    const { rerender } = renderHook(({ e }) => useApiErrorAlert(e), {
      initialProps: { e: { detail: 'Error 1' } },
    })

    expect(mockShowError).toHaveBeenCalledTimes(1)

    rerender({ e: { detail: 'Error 2' } })
    expect(mockShowError).toHaveBeenCalledTimes(2)
  })

  it('resets deduplication when error becomes null', () => {
    type ErrorProps = { e: { detail: string } | null }
    const initialProps: ErrorProps = { e: { detail: 'Error' } }
    const { rerender } = renderHook(({ e }: ErrorProps) => useApiErrorAlert(e), {
      initialProps,
    })

    expect(mockShowError).toHaveBeenCalledTimes(1)

    rerender({ e: null })
    expect(mockShowError).toHaveBeenCalledTimes(1)

    rerender({ e: { detail: 'Error' } })
    expect(mockShowError).toHaveBeenCalledTimes(2)
  })

  it('uses error title from error object', () => {
    renderHook(() => useApiErrorAlert({ title: 'Validation Error', detail: 'Field required' }))

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Validation Error', description: 'Field required' })
  })
})
