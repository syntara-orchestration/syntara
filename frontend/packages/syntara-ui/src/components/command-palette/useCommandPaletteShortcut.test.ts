import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useCommandPaletteShortcut } from './useCommandPaletteShortcut'

function pressKey(init: KeyboardEventInit) {
  const event = new KeyboardEvent('keydown', { bubbles: true, ...init })
  const preventDefault = vi.spyOn(event, 'preventDefault')
  document.dispatchEvent(event)
  return preventDefault
}

describe('useCommandPaletteShortcut', () => {
  it('toggles on Ctrl+K and prevents the browser default', () => {
    const onToggle = vi.fn()
    renderHook(() => useCommandPaletteShortcut({ onToggle }))

    const preventDefault = pressKey({ key: 'k', ctrlKey: true })

    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(preventDefault).toHaveBeenCalled()
  })

  it('toggles on Meta+K', () => {
    const onToggle = vi.fn()
    renderHook(() => useCommandPaletteShortcut({ onToggle }))

    pressKey({ key: 'k', metaKey: true })

    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('ignores unrelated shortcuts', () => {
    const onToggle = vi.fn()
    renderHook(() => useCommandPaletteShortcut({ onToggle }))

    pressKey({ key: 'k' })
    pressKey({ key: 'k', ctrlKey: true, shiftKey: true })

    expect(onToggle).not.toHaveBeenCalled()
  })

  it('removes the listener on unmount', () => {
    const onToggle = vi.fn()
    const { unmount } = renderHook(() => useCommandPaletteShortcut({ onToggle }))

    unmount()
    pressKey({ key: 'k', ctrlKey: true })

    expect(onToggle).not.toHaveBeenCalled()
  })
})
