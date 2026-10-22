export const COMMAND_PALETTE_SEARCH_ID = 'command-palette-search'
export const COMMAND_PALETTE_RESULTS_ID = 'command-palette-results'

export function commandPaletteOptionId(itemId: string): string {
  return `command-palette-option-${itemId.replaceAll(/[^A-Za-z0-9_-]/g, '-')}`
}
