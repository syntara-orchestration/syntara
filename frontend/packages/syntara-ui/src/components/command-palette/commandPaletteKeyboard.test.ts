import { describe, expect, it } from 'vitest'

import { applyPaletteKey } from './commandPaletteKeyboard'
import { COMMAND_PALETTE_CATEGORY, type CommandPaletteItem } from './commandPaletteTypes'

const items: CommandPaletteItem[] = [
  {
    id: 'a',
    category: COMMAND_PALETTE_CATEGORY.PAGE,
    categoryLabel: 'Page',
    title: 'A',
    to: '/a',
  },
  {
    id: 'b',
    category: COMMAND_PALETTE_CATEGORY.PAGE,
    categoryLabel: 'Page',
    title: 'B',
    to: '/b',
  },
]

describe('applyPaletteKey', () => {
  it('does not activate a result on Enter before the user highlights one', () => {
    expect(applyPaletteKey('Enter', items, -1).chosen).toBeUndefined()
  })

  it('starts highlighting at the first result on ArrowDown', () => {
    expect(applyPaletteKey('ArrowDown', items, -1).nextIndex).toBe(0)
  })

  it('activates the highlighted result on Enter', () => {
    expect(applyPaletteKey('Enter', items, 1).chosen?.id).toBe('b')
  })
})
