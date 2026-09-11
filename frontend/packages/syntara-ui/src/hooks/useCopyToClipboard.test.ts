import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopyToClipboard } from './useCopyToClipboard'

describe('useCopyToClipboard', () => {
  const writeTextMock = vi.fn()

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: writeTextMock },
    })
    writeTextMock.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    writeTextMock.mockClear()
  })

  it('starts with isCopied as false', () => {
    const { result } = renderHook(() => useCopyToClipboard())
    expect(result.current.isCopied).toBe(false)
  })

  it('sets isCopied to true after successful copy', async () => {
    const { result } = renderHook(() => useCopyToClipboard())

    act(() => {
      result.current.copy('hello')
    })
    await act(() => Promise.resolve())

    expect(writeTextMock).toHaveBeenCalledWith('hello')
    expect(result.current.isCopied).toBe(true)
  })

  it('resets isCopied after feedback timeout', async () => {
    const { result } = renderHook(() => useCopyToClipboard())

    act(() => {
      result.current.copy('hello')
    })
    await act(() => Promise.resolve())

    expect(result.current.isCopied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(result.current.isCopied).toBe(false)
  })

  it('clears previous timer on rapid copy calls', async () => {
    const { result } = renderHook(() => useCopyToClipboard())

    act(() => {
      result.current.copy('first')
    })
    await act(() => Promise.resolve())
    expect(result.current.isCopied).toBe(true)

    // Second copy should clear the previous timer
    writeTextMock.mockResolvedValueOnce(undefined)
    act(() => {
      result.current.copy('second')
    })
    // Flush the microtask queue twice — detachPromise wraps in Promise.resolve
    await act(() => Promise.resolve())
    await act(() => Promise.resolve())

    expect(writeTextMock).toHaveBeenCalledTimes(2)
    expect(result.current.isCopied).toBe(true)
  })

  it('does not set isCopied when clipboard fails', async () => {
    writeTextMock.mockRejectedValueOnce(new Error('denied'))

    const { result } = renderHook(() => useCopyToClipboard())

    act(() => {
      result.current.copy('fail')
    })
    await act(() => Promise.resolve())

    expect(result.current.isCopied).toBe(false)
  })

  it('does nothing when clipboard API is unavailable', () => {
    Object.assign(navigator, { clipboard: undefined })

    const { result } = renderHook(() => useCopyToClipboard())

    act(() => {
      result.current.copy('noop')
    })

    expect(result.current.isCopied).toBe(false)
  })

  it('clears timer on unmount', async () => {
    const { result, unmount } = renderHook(() => useCopyToClipboard())

    act(() => {
      result.current.copy('hello')
    })
    await act(() => Promise.resolve())

    expect(result.current.isCopied).toBe(true)
    unmount()
  })
})
