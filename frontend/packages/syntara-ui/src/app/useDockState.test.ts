import { renderHook, act } from '@testing-library/react'
import { createElement, createRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { type DockState, DockStateContext, useDockState, useDockStateProvider } from './useDockState'

type MatchMediaListener = (e: { matches: boolean }) => void

function createMockMatchMedia(initialMatches: boolean) {
  const listeners = new Set<MatchMediaListener>()

  const mql = {
    matches: initialMatches,
    media: '',
    addEventListener: vi.fn((_event: string, handler: MatchMediaListener) => {
      listeners.add(handler)
    }),
    removeEventListener: vi.fn((_event: string, handler: MatchMediaListener) => {
      listeners.delete(handler)
    }),
  }

  function trigger(matches: boolean) {
    mql.matches = matches
    for (const listener of listeners) listener({ matches })
  }

  return { mql, trigger, listeners }
}

describe('useDockStateProvider', () => {
  let mockMql: ReturnType<typeof createMockMatchMedia>

  beforeEach(() => {
    vi.useFakeTimers()
    mockMql = createMockMatchMedia(false)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => mockMql.mql)
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('initializes with dock collapsed on desktop', () => {
    const { result } = renderHook(() => useDockStateProvider())

    expect(result.current.isDockExpanded).toBe(false)
    expect(result.current.isDockTextExpanded).toBe(false)
    expect(result.current.isMobile).toBe(false)
  })

  it('initializes isMobile true when viewport is below breakpoint', () => {
    mockMql = createMockMatchMedia(true)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => mockMql.mql)
    )

    const { result } = renderHook(() => useDockStateProvider())

    expect(result.current.isMobile).toBe(true)
  })

  it('onToggleDock toggles isDockTextExpanded on desktop', () => {
    const { result } = renderHook(() => useDockStateProvider())

    act(() => result.current.onToggleDock())
    expect(result.current.isDockTextExpanded).toBe(true)

    act(() => result.current.onToggleDock())
    expect(result.current.isDockTextExpanded).toBe(false)
  })

  it('onToggleDock toggles isDockExpanded on mobile', () => {
    mockMql = createMockMatchMedia(true)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => mockMql.mql)
    )

    const { result } = renderHook(() => useDockStateProvider())

    act(() => result.current.onToggleDock())
    expect(result.current.isDockExpanded).toBe(true)

    act(() => result.current.onToggleDock())
    expect(result.current.isDockExpanded).toBe(false)
  })

  it('onMobileToggle toggles isDockExpanded', () => {
    const { result } = renderHook(() => useDockStateProvider())

    act(() => result.current.onMobileToggle())
    expect(result.current.isDockExpanded).toBe(true)

    act(() => result.current.onMobileToggle())
    expect(result.current.isDockExpanded).toBe(false)
  })

  it('updates isMobile when matchMedia listener fires', () => {
    const { result } = renderHook(() => useDockStateProvider())

    expect(result.current.isMobile).toBe(false)

    act(() => mockMql.trigger(true))
    expect(result.current.isMobile).toBe(true)

    act(() => mockMql.trigger(false))
    expect(result.current.isMobile).toBe(false)
  })

  it('removes matchMedia listener on unmount', () => {
    const { unmount } = renderHook(() => useDockStateProvider())

    unmount()

    expect(mockMql.mql.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function))
  })

  it('transfers focus to docked toggle after mobile toggle with delay', async () => {
    const mockFocus = vi.fn()
    const { result } = renderHook(() => useDockStateProvider())

    Object.defineProperty(result.current.dockedToggleRef, 'current', {
      value: { focus: mockFocus },
      writable: true,
    })

    act(() => result.current.onMobileToggle())
    expect(mockFocus).not.toHaveBeenCalled()

    await act(() => vi.advanceTimersByTime(200))
    expect(mockFocus).toHaveBeenCalledOnce()
  })

  it('transfers focus to mobile toggle when closing dock on mobile', async () => {
    mockMql = createMockMatchMedia(true)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => mockMql.mql)
    )

    const mockFocus = vi.fn()
    const { result } = renderHook(() => useDockStateProvider())

    Object.defineProperty(result.current.mobileToggleRef, 'current', {
      value: { focus: mockFocus },
      writable: true,
    })

    act(() => result.current.onToggleDock())
    expect(result.current.isDockExpanded).toBe(true)

    act(() => result.current.onToggleDock())

    await act(() => vi.advanceTimersByTime(200))
    expect(mockFocus).toHaveBeenCalledOnce()
  })

  it('handles missing matchMedia gracefully', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { result } = renderHook(() => useDockStateProvider())
    expect(result.current.isMobile).toBe(false)
  })

  it('clears focus timer on unmount', async () => {
    const mockFocus = vi.fn()
    const { result, unmount } = renderHook(() => useDockStateProvider())

    Object.defineProperty(result.current.dockedToggleRef, 'current', {
      value: { focus: mockFocus },
      writable: true,
    })

    act(() => result.current.onMobileToggle())
    unmount()

    await act(() => vi.advanceTimersByTime(200))
    expect(mockFocus).not.toHaveBeenCalled()
  })
})

describe('useDockState', () => {
  it('throws when called outside of AppShell context', () => {
    expect(() => renderHook(() => useDockState())).toThrow('useDockState must be used within AppShell')
  })

  it('returns context value when used within a provider', () => {
    const mockState: DockState = {
      isDockExpanded: false,
      isDockTextExpanded: true,
      isMobile: false,
      dockedToggleRef: createRef(),
      mobileToggleRef: createRef(),
      onToggleDock: vi.fn(),
      onMobileToggle: vi.fn(),
    }
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(DockStateContext.Provider, { value: mockState }, children)

    const { result } = renderHook(() => useDockState(), { wrapper })
    expect(result.current).toBe(mockState)
  })
})
