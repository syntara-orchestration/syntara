import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useShowAfterDelay } from './useShowAfterDelay'

describe('useShowAfterDelay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('stays hidden until the delay elapses while active', () => {
    const { result } = renderHook(() => useShowAfterDelay(true, 300))

    expect(result.current).toBe(false)

    act(() => {
      vi.advanceTimersByTime(299)
    })
    expect(result.current).toBe(false)

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current).toBe(true)
  })

  it('hides immediately when active becomes false', () => {
    const { result, rerender } = renderHook(({ active }) => useShowAfterDelay(active, 300), {
      initialProps: { active: true },
    })

    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(result.current).toBe(true)

    rerender({ active: false })
    expect(result.current).toBe(false)
  })

  it('clears a pending timer when active toggles off before the delay', () => {
    const { result, rerender } = renderHook(({ active }) => useShowAfterDelay(active, 300), {
      initialProps: { active: true },
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })
    rerender({ active: false })
    expect(result.current).toBe(false)

    rerender({ active: true })
    act(() => {
      vi.advanceTimersByTime(299)
    })
    expect(result.current).toBe(false)

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current).toBe(true)
  })
})
