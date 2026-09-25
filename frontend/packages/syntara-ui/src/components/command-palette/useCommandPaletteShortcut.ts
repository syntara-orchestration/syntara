import { useEffect } from 'react'

import { isCommandPaletteToggleEvent } from './commandPaletteShortcut'

type UseCommandPaletteShortcutOptions = {
  /** Toggle open/closed. Ctrl/Cmd+K always calls this. */
  onToggle: () => void
}

/**
 * Global Ctrl/Cmd+K listener. Capture phase so the in-app finder wins over
 * browser search (Chrome Ctrl/Cmd+K) and still works while an input is focused.
 */
export function useCommandPaletteShortcut({ onToggle }: UseCommandPaletteShortcutOptions): void {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (!isCommandPaletteToggleEvent(event)) return
      event.preventDefault()
      event.stopPropagation()
      onToggle()
    }

    document.addEventListener('keydown', handleKeyDown, { capture: true })
    return () => document.removeEventListener('keydown', handleKeyDown, { capture: true })
  }, [onToggle])
}
