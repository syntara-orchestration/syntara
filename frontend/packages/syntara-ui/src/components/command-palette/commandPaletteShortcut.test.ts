import { describe, expect, it } from 'vitest'

import { commandPaletteShortcutLabel, isCommandPaletteToggleEvent } from './commandPaletteShortcut'

function keyEvent(init: KeyboardEventInit): KeyboardEvent {
  return new KeyboardEvent('keydown', init)
}

describe('isCommandPaletteToggleEvent', () => {
  it('matches Ctrl+K and Meta+K', () => {
    expect(isCommandPaletteToggleEvent(keyEvent({ key: 'k', ctrlKey: true }))).toBe(true)
    expect(isCommandPaletteToggleEvent(keyEvent({ key: 'K', metaKey: true }))).toBe(true)
  })

  it('rejects shifted, alt, or unmodified K', () => {
    expect(isCommandPaletteToggleEvent(keyEvent({ key: 'k' }))).toBe(false)
    expect(isCommandPaletteToggleEvent(keyEvent({ key: 'k', ctrlKey: true, shiftKey: true }))).toBe(false)
    expect(isCommandPaletteToggleEvent(keyEvent({ key: 'k', ctrlKey: true, altKey: true }))).toBe(false)
  })
})

describe('commandPaletteShortcutLabel', () => {
  it('uses the command glyph on macOS user agents', () => {
    expect(commandPaletteShortcutLabel('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')).toBe('⌘K')
  })

  it('uses Ctrl+K on other platforms', () => {
    expect(commandPaletteShortcutLabel('Mozilla/5.0 (X11; Linux x86_64)')).toBe('Ctrl+K')
  })
})
