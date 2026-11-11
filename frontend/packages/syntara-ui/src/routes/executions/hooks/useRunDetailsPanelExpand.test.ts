import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { useRunDetailsPanelExpand } from './useRunDetailsPanelExpand'

describe('useRunDetailsPanelExpand', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not expose expand control when disabled', () => {
    const setPanelHeight = vi.fn()
    const { result } = renderHook(() => useRunDetailsPanelExpand(300, setPanelHeight, false))

    expect(result.current.panelExpandControl).toBeUndefined()
    expect(result.current.isPanelExpanded).toBe(false)
  })

  it('expands and collapses while restoring the prior height', () => {
    const setPanelHeight = vi.fn()
    const { result, rerender } = renderHook(
      ({ height }: { height: number }) => useRunDetailsPanelExpand(height, setPanelHeight, true),
      { initialProps: { height: 300 } }
    )

    act(() => {
      result.current.panelExpandControl?.onToggle()
    })
    expect(result.current.isPanelExpanded).toBe(true)

    rerender({ height: 280 })
    act(() => {
      result.current.panelExpandControl?.onToggle()
    })
    expect(result.current.isPanelExpanded).toBe(false)
    expect(setPanelHeight).toHaveBeenCalledWith(300)
  })

  it('collapses when the panel becomes inactive', () => {
    const setPanelHeight = vi.fn()
    const { result, rerender } = renderHook(
      ({ active }: { active: boolean }) => useRunDetailsPanelExpand(320, setPanelHeight, true, active),
      { initialProps: { active: true } }
    )

    act(() => {
      result.current.panelExpandControl?.onToggle()
    })
    expect(result.current.isPanelExpanded).toBe(true)

    rerender({ active: false })

    expect(result.current.isPanelExpanded).toBe(false)
    expect(setPanelHeight).toHaveBeenCalledWith(320)
  })

  it('does not collapse on Escape when the event was already handled', () => {
    const setPanelHeight = vi.fn()
    const { result } = renderHook(() => useRunDetailsPanelExpand(400, setPanelHeight, true))

    act(() => {
      result.current.panelExpandControl?.onToggle()
    })

    act(() => {
      const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
      event.preventDefault()
      document.dispatchEvent(event)
    })

    expect(result.current.isPanelExpanded).toBe(true)
    expect(setPanelHeight).not.toHaveBeenCalled()
  })

  it('collapses on Escape while expanded', () => {
    const setPanelHeight = vi.fn()
    const { result } = renderHook(() => useRunDetailsPanelExpand(400, setPanelHeight, true))

    act(() => {
      result.current.panelExpandControl?.onToggle()
    })

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    })

    expect(result.current.isPanelExpanded).toBe(false)
    expect(setPanelHeight).toHaveBeenCalledWith(400)
  })
})
