export const COMMAND_PALETTE_HOTKEY = 'k'

export function isCommandPaletteToggleEvent(event: KeyboardEvent): boolean {
  if (event.altKey || event.shiftKey) return false
  if (!event.metaKey && !event.ctrlKey) return false
  return event.key.toLowerCase() === COMMAND_PALETTE_HOTKEY
}

export function commandPaletteShortcutLabel(userAgent: string = navigator.userAgent): string {
  return userAgent.includes('Mac') ? '⌘K' : 'Ctrl+K'
}
