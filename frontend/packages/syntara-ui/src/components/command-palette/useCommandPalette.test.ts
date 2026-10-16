import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useCommandPalette } from './useCommandPalette'

describe('useCommandPalette', () => {
  it('throws when used outside CommandPaletteProvider', () => {
    expect(() => renderHook(() => useCommandPalette())).toThrow(
      'useCommandPalette must be used within CommandPaletteProvider'
    )
  })
})
