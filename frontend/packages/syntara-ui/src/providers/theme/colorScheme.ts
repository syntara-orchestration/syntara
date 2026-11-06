/**
 * Color scheme: PatternFly `pf-v6-theme-dark` on `<html>` selects light vs dark.
 * Contrast classes (`pf-v6-theme-glass`, `pf-v6-theme-high-contrast`) are owned by `contrastMode.ts`.
 * Keep `resolveColorScheme` and `applyDocumentColorScheme` in sync with the inline script in `index.html`.
 */
/** `localStorage` key for the light, dark, or system color-scheme preference. */
export const COLOR_SCHEME_STORAGE_KEY = 'syntara-ui-color-scheme'

/** Resolved appearance: PatternFly light (no `pf-v6-theme-dark`) or dark. */
export type ColorScheme = 'light' | 'dark'

/** User choice. `system` follows `prefers-color-scheme` (else dark). */
export type ColorSchemePreference = 'system' | ColorScheme

/** Returns a valid stored preference, or `null` if missing, invalid, or storage is unavailable. */
export function readStoredColorSchemePreference(): ColorSchemePreference | null {
  try {
    const value = globalThis.localStorage?.getItem(COLOR_SCHEME_STORAGE_KEY)
    if (value === 'system' || value === 'light' || value === 'dark') {
      return value
    }
  } catch {
    // Storage may be unavailable (private mode, SSR).
  }
  return null
}

/**
 * Effective scheme: explicit light/dark preference, else `prefers-color-scheme`, else `dark`.
 * A missing preference and an explicit `system` preference resolve the same way.
 * Must stay aligned with `index.html` inline bootstrap script.
 */
export function resolveColorScheme(): ColorScheme {
  const stored = readStoredColorSchemePreference()
  if (stored === 'light' || stored === 'dark') {
    return stored
  }
  try {
    if (globalThis.matchMedia?.('(prefers-color-scheme: light)').matches) {
      return 'light'
    }
    if (globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches) {
      return 'dark'
    }
  } catch {
    // matchMedia may be unavailable.
  }
  return 'dark'
}

/** True when color scheme should track the OS, including when nothing is stored yet. */
export function colorSchemeFollowsSystem(): boolean {
  const stored = readStoredColorSchemePreference()
  return stored === null || stored === 'system'
}

/** Reads the active scheme from `document.documentElement` (`pf-v6-theme-dark`). */
export function getColorSchemeFromDocument(): ColorScheme {
  return document.documentElement.classList.contains('pf-v6-theme-dark') ? 'dark' : 'light'
}

/**
 * Sets or clears `pf-v6-theme-dark` on `<html>` to match `scheme`.
 * Does not change contrast classes.
 */
export function applyDocumentColorScheme(scheme: ColorScheme): void {
  document.documentElement.classList.toggle('pf-v6-theme-dark', scheme === 'dark')
}

/** Writes `preference` to `localStorage` under {@link COLOR_SCHEME_STORAGE_KEY}; no-ops if storage fails. */
export function persistColorScheme(preference: ColorSchemePreference): void {
  try {
    globalThis.localStorage?.setItem(COLOR_SCHEME_STORAGE_KEY, preference)
  } catch {
    // ignore
  }
}

/**
 * Applies {@link resolveColorScheme} to the document. Idempotent; safe on every load
 * (inline `index.html` script + `main.tsx` init).
 */
export function ensureDocumentColorScheme(): void {
  applyDocumentColorScheme(resolveColorScheme())
}
