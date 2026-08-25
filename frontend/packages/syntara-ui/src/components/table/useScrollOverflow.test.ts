import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useScrollOverflow } from './useScrollOverflow'

type ResizeObserverCallback = (entries: ResizeObserverEntry[]) => void

function createMockScrollElement(overrides: { scrollHeight: number; clientHeight: number; scrollTop: number }) {
  const el = document.createElement('div')
  Object.defineProperty(el, 'scrollHeight', { get: () => overrides.scrollHeight, configurable: true })
  Object.defineProperty(el, 'clientHeight', { get: () => overrides.clientHeight, configurable: true })
  Object.defineProperty(el, 'scrollTop', { get: () => overrides.scrollTop, configurable: true })
  return el
}

/**
 * Mounts callback refs the way React 19 would: assign both nodes, keep cleanups for unmount.
 */
function attachScrollOverflow(
  scrollRef: (node: HTMLElement | null) => (() => void) | void,
  wrapperRef: (node: HTMLElement | null) => (() => void) | void,
  scrollEl: HTMLElement,
  wrapperEl: HTMLElement
) {
  let cleanupScroll: (() => void) | void
  let cleanupWrapper: (() => void) | void
  act(() => {
    cleanupWrapper = wrapperRef(wrapperEl)
    cleanupScroll = scrollRef(scrollEl)
  })
  return () => {
    act(() => {
      cleanupScroll?.()
      cleanupWrapper?.()
    })
  }
}

describe('useScrollOverflow', () => {
  let resizeCallback: ResizeObserverCallback | null = null
  const observeSpy = vi.fn()
  const disconnectSpy = vi.fn()

  beforeEach(() => {
    resizeCallback = null
    globalThis.ResizeObserver = class MockResizeObserver {
      constructor(cb: ResizeObserverCallback) {
        resizeCallback = cb
      }
      observe = observeSpy
      unobserve = vi.fn()
      disconnect = disconnectSpy
    } as unknown as typeof ResizeObserver
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sets --syn-scroll-fade-opacity to 1 when content overflows and is not near the bottom', () => {
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 0 })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)

    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('1')
  })

  it('sets --syn-scroll-fade-opacity to 0 when content does not overflow', () => {
    const scrollEl = createMockScrollElement({ scrollHeight: 300, clientHeight: 300, scrollTop: 0 })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)

    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('0')
  })

  it('sets --syn-scroll-fade-opacity to 0 when scrolled to the bottom', () => {
    // scrollableRemaining = 500 - 200 - 300 = 0
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 200 })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)

    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('0')
  })

  it('sets a proportional opacity when partially scrolled within the fade distance', () => {
    // scrollableRemaining = 500 - 140 - 300 = 60; fadeDistance = 120 (fallback); ratio = 0.5
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 140 })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)

    expect(Number.parseFloat(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity'))).toBeCloseTo(0.5)
  })

  it('reads --syn-scroll-fade-distance from the scroll element computed style', () => {
    // scrollableRemaining = 500 - 140 - 300 = 60; fadeDistance = 80; t = 0.75; smoothstep(0.75) = 0.84375
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 140 })
    scrollEl.style.setProperty('--syn-scroll-fade-distance', '80')
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)

    expect(Number.parseFloat(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity'))).toBeCloseTo(0.84375)
  })

  it('clamps opacity to 1 when scrollable remaining exceeds the fade distance', () => {
    // scrollableRemaining = 500 - 0 - 300 = 200 > 120; ratio clamped to 1
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 0 })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)

    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('1')
  })

  it('updates --syn-scroll-fade-opacity when a scroll event fires', () => {
    const scrollTop = { value: 0 }
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 0 })
    Object.defineProperty(scrollEl, 'scrollTop', { get: () => scrollTop.value, configurable: true })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)
    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('1')

    scrollTop.value = 200
    act(() => {
      scrollEl.dispatchEvent(new Event('scroll'))
    })

    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('0')
  })

  it('updates --syn-scroll-fade-opacity when the ResizeObserver fires', () => {
    const scrollHeight = { value: 300 }
    const scrollEl = createMockScrollElement({ scrollHeight: 300, clientHeight: 300, scrollTop: 0 })
    Object.defineProperty(scrollEl, 'scrollHeight', { get: () => scrollHeight.value, configurable: true })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)
    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('0')

    scrollHeight.value = 500
    act(() => {
      resizeCallback?.([] as ResizeObserverEntry[])
    })

    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('1')
  })

  it('attaches the scroll listener with the passive option', () => {
    const scrollEl = createMockScrollElement({ scrollHeight: 300, clientHeight: 300, scrollTop: 0 })
    const wrapperEl = document.createElement('div')
    const addEventSpy = vi.spyOn(scrollEl, 'addEventListener')
    const { result } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)

    expect(addEventSpy).toHaveBeenCalledWith('scroll', expect.any(Function), { passive: true })
  })

  it('removes the scroll listener and disconnects ResizeObserver via ref cleanup', () => {
    const scrollEl = createMockScrollElement({ scrollHeight: 300, clientHeight: 300, scrollTop: 0 })
    const wrapperEl = document.createElement('div')
    const removeEventSpy = vi.spyOn(scrollEl, 'removeEventListener')
    const { result } = renderHook(() => useScrollOverflow())

    const detach = attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)
    detach()

    expect(removeEventSpy).toHaveBeenCalledWith('scroll', expect.any(Function))
    expect(disconnectSpy).toHaveBeenCalled()
  })

  it('does nothing when only one ref is attached', () => {
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 0 })
    const wrapperEl = document.createElement('div')
    const { result } = renderHook(() => useScrollOverflow())

    act(() => {
      result.current.scrollRef(scrollEl)
    })
    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('')

    act(() => {
      result.current.wrapperRef(wrapperEl)
    })
    expect(wrapperEl.style.getPropertyValue('--syn-scroll-fade-opacity')).toBe('1')
  })

  it('keeps stable callback ref identities across re-renders', () => {
    const { result, rerender } = renderHook(() => useScrollOverflow())
    const { scrollRef, wrapperRef } = result.current

    rerender()

    expect(result.current.scrollRef).toBe(scrollRef)
    expect(result.current.wrapperRef).toBe(wrapperRef)
  })

  it('does not re-attach listeners when the parent re-renders with stable refs', () => {
    const scrollEl = createMockScrollElement({ scrollHeight: 500, clientHeight: 300, scrollTop: 0 })
    const wrapperEl = document.createElement('div')
    const addEventSpy = vi.spyOn(scrollEl, 'addEventListener')
    const { result, rerender } = renderHook(() => useScrollOverflow())

    attachScrollOverflow(result.current.scrollRef, result.current.wrapperRef, scrollEl, wrapperEl)
    expect(addEventSpy).toHaveBeenCalledTimes(1)
    expect(observeSpy).toHaveBeenCalledTimes(1)

    rerender()

    expect(addEventSpy).toHaveBeenCalledTimes(1)
    expect(observeSpy).toHaveBeenCalledTimes(1)
    expect(disconnectSpy).not.toHaveBeenCalled()
  })
})
