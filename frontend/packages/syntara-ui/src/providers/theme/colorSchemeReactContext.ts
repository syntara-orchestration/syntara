import { createContext } from 'react'

import type { ColorScheme, ColorSchemePreference } from './colorScheme'
import type { ContrastMode, ContrastPreference } from './contrastMode'

/** React context value for color scheme and contrast mode. */
export type ColorSchemeContextValue = {
  /** Resolved light or dark appearance. */
  colorScheme: ColorScheme
  /** Stored color-scheme choice, or `system` when nothing is stored. */
  colorSchemePreference: ColorSchemePreference
  setColorScheme: (preference: ColorSchemePreference) => void
  toggleColorScheme: () => void
  /** Resolved contrast treatment on `<html>`. */
  contrastMode: ContrastMode
  /** Stored contrast choice, or `system` when nothing is stored. */
  contrastPreference: ContrastPreference
  setContrastMode: (preference: ContrastPreference) => void
}

/** Context for PatternFly color scheme and contrast; default `null` outside {@link ColorSchemeProvider}. */
export const ColorSchemeContext = createContext<ColorSchemeContextValue | null>(null)
