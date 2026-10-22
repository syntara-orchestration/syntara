import { createContext, use } from 'react'

export type CommandPaletteContextValue = {
  /** Whether the palette is visible. */
  isOpen: boolean
  /** Open the palette. */
  open: () => void
  /** Close the palette. */
  close: () => void
  /** Toggle the palette. Bound to Ctrl/Cmd+K. */
  toggle: () => void
}

export const CommandPaletteContext = createContext<CommandPaletteContextValue | null>(null)

export function useCommandPalette(): CommandPaletteContextValue {
  const value = use(CommandPaletteContext)
  if (!value) {
    throw new Error('useCommandPalette must be used within CommandPaletteProvider')
  }
  return value
}
