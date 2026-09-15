import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { generateUUID } from '../../../../utils/generateUUID'

import { useTestSignIn } from './useTestSignIn'

vi.mock('../../../../utils/generateUUID', () => ({ generateUUID: vi.fn() }))

const RESULT_STORAGE_KEY = 'syntara-test-signin'

describe('useTestSignIn', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    vi.spyOn(globalThis, 'open').mockReturnValue({ closed: false } as Window)
    vi.mocked(generateUUID).mockReturnValue('test-nonce-123')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('does nothing when providerId is not set', () => {
    const onResult = vi.fn()
    const { result } = renderHook(() => useTestSignIn({ onResult }))

    act(() => result.current.openTestSignIn())

    expect(globalThis.open).not.toHaveBeenCalled()
    expect(result.current.isListening).toBe(false)
  })

  it('opens popup and sets isListening on openTestSignIn', () => {
    const onResult = vi.fn()
    const { result } = renderHook(() => useTestSignIn({ providerId: 'prov-1', onResult }))

    act(() => result.current.openTestSignIn())

    expect(globalThis.open).toHaveBeenCalledWith(
      expect.stringContaining('provider_id=prov-1'),
      'test-signin',
      'width=600,height=700'
    )
    expect(result.current.isListening).toBe(true)
    expect(localStorage.getItem('syntara-test-signin-nonce')).toBe('test-nonce-123')
  })

  it('polls localStorage and calls onResult when result appears', async () => {
    const onResult = vi.fn()
    const { result } = renderHook(() => useTestSignIn({ providerId: 'prov-1', onResult }))

    act(() => result.current.openTestSignIn())

    const payload = JSON.stringify({
      type: 'test-signin',
      nonce: 'test-nonce-123',
      claims: { groups: ['admin', 'dev'] },
    })
    localStorage.setItem(RESULT_STORAGE_KEY, payload)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200)
    })

    expect(onResult).toHaveBeenCalledWith({ groups: ['admin', 'dev'] })
    expect(result.current.isListening).toBe(false)
  })

  it('does not call onResult when nonce does not match', async () => {
    const onResult = vi.fn()
    const { result } = renderHook(() => useTestSignIn({ providerId: 'prov-1', onResult }))

    act(() => result.current.openTestSignIn())

    localStorage.setItem(
      RESULT_STORAGE_KEY,
      JSON.stringify({ type: 'test-signin', nonce: 'wrong-nonce', claims: { groups: ['admin'] } })
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200)
    })

    expect(onResult).not.toHaveBeenCalled()
    expect(localStorage.getItem(RESULT_STORAGE_KEY)).not.toBeNull()
  })

  it('ignores invalid JSON in localStorage', async () => {
    const onResult = vi.fn()
    const { result } = renderHook(() => useTestSignIn({ providerId: 'prov-1', onResult }))

    act(() => result.current.openTestSignIn())

    localStorage.setItem(RESULT_STORAGE_KEY, 'not-json')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200)
    })

    expect(onResult).not.toHaveBeenCalled()
  })

  it('ignores result with missing claims', async () => {
    const onResult = vi.fn()
    const { result } = renderHook(() => useTestSignIn({ providerId: 'prov-1', onResult }))

    act(() => result.current.openTestSignIn())

    localStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify({ type: 'test-signin', nonce: 'test-nonce-123' }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200)
    })

    expect(onResult).not.toHaveBeenCalled()
  })

  it('resets isListening and calls onError after timeout expires without result', async () => {
    const onResult = vi.fn()
    const onError = vi.fn()
    const { result } = renderHook(() => useTestSignIn({ providerId: 'prov-1', onResult, onError }))

    act(() => result.current.openTestSignIn())
    expect(result.current.isListening).toBe(true)

    // Advance past the 2-minute timeout
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_200)
    })
    expect(result.current.isListening).toBe(false)
    expect(onResult).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalled()
  })

  it('cleans up poll timer on unmount', () => {
    const clearSpy = vi.spyOn(globalThis, 'clearInterval')
    const onResult = vi.fn()
    const { result, unmount } = renderHook(() => useTestSignIn({ providerId: 'prov-1', onResult }))

    act(() => result.current.openTestSignIn())
    unmount()

    expect(clearSpy).toHaveBeenCalled()
  })
})
