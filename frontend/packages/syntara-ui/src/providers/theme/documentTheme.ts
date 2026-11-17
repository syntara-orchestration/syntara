import { applyDocumentColorScheme, resolveColorScheme } from './colorScheme'
import { applyDocumentContrast, resolveContrastMode } from './contrastMode'

/**
 * Applies the resolved color scheme and contrast mode to `<html>`.
 * Idempotent. Called from `main.tsx` after the inline `index.html` bootstrap.
 */
export function ensureDocumentTheme(): void {
  applyDocumentColorScheme(resolveColorScheme())
  applyDocumentContrast(resolveContrastMode())
}
