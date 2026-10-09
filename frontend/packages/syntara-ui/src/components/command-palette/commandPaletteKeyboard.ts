import type { CommandPaletteItem } from './commandPaletteTypes'

export type PaletteKeyResult = {
  nextIndex: number
  chosen: CommandPaletteItem | undefined
}

/**
 * Arrow keys move the active option. Enter activates only after an explicit
 * highlight (index >= 0). `-1` means the search field is the sole selection.
 */
export function applyPaletteKey(
  key: string,
  results: readonly CommandPaletteItem[],
  activeIndex: number
): PaletteKeyResult {
  if (results.length === 0) return { nextIndex: -1, chosen: undefined }

  if (key === 'ArrowDown') {
    return { nextIndex: activeIndex < 0 ? 0 : (activeIndex + 1) % results.length, chosen: undefined }
  }
  if (key === 'ArrowUp') {
    return {
      nextIndex: activeIndex < 0 ? results.length - 1 : (activeIndex - 1 + results.length) % results.length,
      chosen: undefined,
    }
  }
  if (key === 'Enter') {
    return { nextIndex: activeIndex, chosen: activeIndex >= 0 ? results[activeIndex] : undefined }
  }
  return { nextIndex: activeIndex, chosen: undefined }
}
