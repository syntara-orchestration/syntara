export const COMMAND_PALETTE_HOTKEY = 'k'

export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  return Boolean(target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]'))
}

export function isCommandPaletteToggleEvent(event: KeyboardEvent): boolean {
  if (event.altKey || event.shiftKey) return false
  if (!event.metaKey && !event.ctrlKey) return false
  if (event.key.toLowerCase() !== COMMAND_PALETTE_HOTKEY) return false
  return !isEditableKeyboardTarget(event.target)
}

export function commandPaletteShortcutLabel(userAgent: string = navigator.userAgent): string {
  return userAgent.includes('Mac') ? '⌘K' : 'Ctrl+K'
}
