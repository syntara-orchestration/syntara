import { useCallback, useMemo, useState } from 'react'

import { CommandPalette } from './CommandPalette'
import { CommandPaletteContext, type CommandPaletteContextValue } from './useCommandPalette'
import { useCommandPaletteShortcut } from './useCommandPaletteShortcut'

/**
 * Provides command-palette open state, the Ctrl/Cmd+K shortcut, and the modal.
 * Mount once inside the authenticated app shell.
 */
export function CommandPaletteProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [isOpen, setIsOpen] = useState(false)
  const open = useCallback(() => setIsOpen(true), [])
  const close = useCallback(() => setIsOpen(false), [])
  const toggle = useCallback(() => setIsOpen((current) => !current), [])
  const value = useMemo<CommandPaletteContextValue>(
    () => ({ isOpen, open, close, toggle }),
    [isOpen, open, close, toggle]
  )

  useCommandPaletteShortcut({ onToggle: toggle })

  return (
    <CommandPaletteContext.Provider value={value}>
      {children}
      <CommandPalette isOpen={isOpen} onClose={close} />
    </CommandPaletteContext.Provider>
  )
}
